"""Điều phối một đợt Article Lane thành workflow bền: preflight → phân tích → nạp DB."""

from __future__ import annotations

import glob
import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Protocol

from src.core import paths
from src.ops import breakers as br
from src.ops import metrics as wave_metrics
from src.ops import trace as tracing
from src.ops.config import PROJECT_ROOT, OpsPaths
from src.ops.order import demote, load_order, save_order
from src.ops.present import FAILURE_CLASS, WAVE_STATUS, alert_card, fmt_datetime, label
from src.ops.procrun import StepResult, python_cmd, run_step
from src.ops.store import OpsStore, iso, now_vn
from src.ops.trace import Tracer

SCRIPTS = PROJECT_ROOT / "scripts"
TASK_DIR = paths.article_packets_dir()
OUT_DIR = paths.agent_outputs_dir("_article")
MIN_COVERAGE = 0.90

_BATCH_LINE = re.compile(r"^\s*(✅|⚠️)\s+(\S+):\s+([A-Z_]+)\s+\((\d+) bài\)\s*(.*)$")


@dataclass
class WaveSpec:
    """Thông số bất biến của một lần chạy đợt.

    Attributes:
        wave_id: Mã đợt, dùng làm tiền tố tên tệp packet.
        target_date: Ngày xuất bản của bài được chọn.
        trigger: Luật kích hoạt (T1, T2, T3, manual, retry).
        level: Mức tự chủ lúc mở đợt (ghi nhận; đợt đã mở luôn chạy trọn tới nạp DB).
        provider: Runner nhận thức.
        attempt: Số lần chạy lại đợt.
        order_hash: Băm standing order lúc mở đợt.
    """

    wave_id: str
    target_date: str
    trigger: str
    level: str
    provider: str = "agy"
    attempt: int = 0
    order_hash: str = ""

    @property
    def workflow_id(self) -> str:
        """Mã workflow idempotent của lần chạy này."""
        base = f"wave-{self.wave_id}"
        return base if self.attempt == 0 else f"{base}-r{self.attempt}"


@dataclass
class AnalyzeOutcome:
    """Kết quả một vòng phân tích hoặc vá.

    Attributes:
        mode: `analyze`, `repair` hoặc `skip`.
        step_outcome: Kết cục của tiến trình bước.
        received: Số bài đã có bản ghi.
        total: Số bài của đợt.
        worst: Lớp lỗi nghiêm trọng nhất trong vòng.
        batches: Danh sách (lô, trạng thái, số bài, lớp lỗi).
    """

    mode: str
    step_outcome: str
    received: int
    total: int
    worst: str
    batches: list[list[Any]] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        """True khi mọi bài đã có bản ghi."""
        return self.total > 0 and self.received >= self.total

    @property
    def coverage(self) -> float:
        """Tỷ lệ bài đã có bản ghi."""
        return self.received / self.total if self.total else 0.0


def parse_batch_lines(text: str) -> list[tuple[str, str, int, str]]:
    """Đọc dòng kết quả từng lô mà `article_run.py --analyze/--repair` in ra.

    Args:
        text: Nhật ký của bước.

    Returns:
        Danh sách (lô, trạng thái, số bài, thông điệp lỗi).
    """
    out = []
    for line in text.splitlines():
        m = _BATCH_LINE.match(line)
        if m:
            out.append((m.group(2), m.group(3), int(m.group(4)), m.group(5).strip()))
    return out


class WaveSteps:
    """Hiện thực từng bước của đợt bằng các lệnh sẵn có của Article Lane.

    Attributes:
        store: Store vận hành.
        cfg: Cấu hình đầy đủ.
        paths: Đường dẫn vận hành.
        breakers: Circuit breaker theo provider.
        executor: Hàm chạy bước, mặc định `run_step`.
        task_dir: Thư mục packet của Article Lane.
        out_dir: Thư mục đầu ra của mô hình.
    """

    def __init__(self, store: OpsStore, cfg: dict, paths: OpsPaths, *,
                 executor: Callable[..., StepResult] = run_step,
                 task_dir: Path = TASK_DIR, out_dir: Path = OUT_DIR,
                 db_probe: Callable[[], tuple[bool, str]] | None = None) -> None:
        """Gắn phụ thuộc của các bước.

        Args:
            store: Store vận hành.
            cfg: Cấu hình đầy đủ.
            paths: Đường dẫn vận hành.
            executor: Hàm chạy bước.
            task_dir: Thư mục packet.
            out_dir: Thư mục đầu ra.
            db_probe: Hàm thử ghi DB vận hành, trả (đạt, lý do).
        """
        self.store = store
        self.cfg = cfg
        self.paths = paths
        self.breakers = br.Breakers(store, cfg["breaker"])
        self.executor = executor
        self.task_dir = task_dir
        self.out_dir = out_dir
        self.db_probe = db_probe or _default_db_probe

    # ── tiện ích ─────────────────────────────────────────────────────────────
    def _deadline(self, step: str) -> float:
        return float(self.cfg["wave"]["deadlines_minutes"].get(step, 10)) * 60

    def _log(self, spec: WaveSpec, step: str) -> Path:
        return self.paths.log_dir / "waves" / spec.wave_id / f"{step}.log"

    @staticmethod
    def _root_id(spec: WaveSpec) -> str:
        return f"{spec.wave_id}.a{spec.attempt}"

    @staticmethod
    def _step_id(spec: WaveSpec, step: str) -> str:
        return f"{spec.wave_id}.a{spec.attempt}.{step}"

    def _tracer(self, spec: WaveSpec) -> Tracer:
        """Tracer của đợt, span mới mặc định nằm dưới span gốc của lần chạy này."""
        return Tracer(self.paths.ops_db, spec.wave_id, parent_id=self._root_id(spec))

    def stop_requested(self, wave_id: str) -> bool:
        """Cho biết người vận hành đã yêu cầu dừng đợt hay chưa.

        Args:
            wave_id: Mã đợt.

        Returns:
            True khi có `AGY_STOP` hoặc lệnh huỷ đợt.
        """
        return self.paths.kill_switch.exists() or bool(self.store.get_state(f"cancel:{wave_id}"))

    def _run(self, spec: WaveSpec, step: str, *args: str,
             progress_fn: Callable[[], object] | None = None,
             silence_s: float | None = None, interruptible: bool = True,
             parent: str | None = None) -> StepResult:
        self.store.upsert_wave(spec.wave_id, step=step)
        self.store.emit("step.started", f"{spec.wave_id}: bắt đầu {step}", actor="wave",
                        wave_id=spec.wave_id, step=step)
        stop_fn = (lambda: self.stop_requested(spec.wave_id)) if interruptible else None
        res = self.executor(python_cmd(SCRIPTS / "article_run.py", *args), cwd=PROJECT_ROOT,
                            log_path=self._log(spec, step), deadline_s=self._deadline(step),
                            progress_fn=progress_fn, silence_s=silence_s, stop_fn=stop_fn,
                            extra_env=self._tracer(spec).child_env(parent) if parent else None)
        level = "info" if res.ok else "error"
        self.store.emit("step.done" if res.ok else "step.failed",
                        f"{spec.wave_id}: {step} → {res.outcome} ({res.duration_s:.0f}s)",
                        level=level, actor="wave", wave_id=spec.wave_id, step=step,
                        data={"rc": res.returncode, "outcome": res.outcome,
                              "tail": res.tail[-1500:] if not res.ok else None})
        return res

    def manifest(self, wave_id: str) -> dict | None:
        """Đọc manifest của đợt nếu đã đóng gói.

        Args:
            wave_id: Mã đợt.

        Returns:
            Nội dung manifest hoặc None.
        """
        p = self.task_dir / f"wave_{wave_id}.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def _output_signature(self, wave_id: str) -> tuple[int, float]:
        files = glob.glob(str(self.out_dir / f"article_{wave_id}_*.output.json"))
        mtimes = [Path(f).stat().st_mtime for f in files if Path(f).exists()]
        return len(files), max(mtimes) if mtimes else 0.0

    def _coverage(self, wave_id: str) -> tuple[int, int]:
        from scripts import article_run as ar

        total = len(ar.wave_article_ids(wave_id))
        received = len(ar.wave_received_ids(wave_id))
        return received, total

    def _count_repair_round(self, wave_id: str) -> None:
        """Ghi một vòng vá vào bộ đếm bền của đợt và của từng bài còn thiếu."""
        from scripts import article_run as ar

        missing = sorted(set(ar.wave_article_ids(wave_id)) - set(ar.wave_received_ids(wave_id)))
        self.store.bump_attempts(missing, wave_id)
        key = f"repair_rounds:{wave_id}"
        self.store.set_state(key, str(int(self.store.get_state(key, "0") or 0) + 1))

    def _has_outputs(self, wave_id: str) -> bool:
        return self._output_signature(wave_id)[0] > 0

    # ── các bước ─────────────────────────────────────────────────────────────
    def preflight(self, spec: WaveSpec) -> tuple[bool, str, bool]:
        """Kiểm điều kiện trước khi tiêu token.

        Args:
            spec: Thông số đợt.

        Returns:
            Bộ ba (đạt, lý do, chờ breaker) — phần tử cuối True khi lý do là provider.
        """
        self.store.upsert_wave(spec.wave_id, status="PREFLIGHT", step="preflight")
        tr = self._tracer(spec)
        tr.begin(f"wave-{spec.wave_id}", "workflow", "master-orchestrator",
                 span_id=self._root_id(spec), parent_id=None, trigger=spec.trigger,
                 level=spec.level, provider=spec.provider, target_date=spec.target_date,
                 attempt=spec.attempt, order_hash=spec.order_hash)
        with tracing.span("preflight", "step", "master-orchestrator", tracer=tr,
                          span_id=self._step_id(spec, "preflight"),
                          entrypoint="article_run.py --check-prefix") as sp:
            ok, reason, wait = self._preflight_checks(spec, sp.id)
            sp.set(ok=ok, reason=reason[:200], breaker_wait=wait)
            if not ok:
                sp.status = "parked"
            return ok, reason, wait

    def _preflight_checks(self, spec: WaveSpec, parent: str | None) -> tuple[bool, str, bool]:
        if self.stop_requested(spec.wave_id):
            return False, "Có cờ dừng AGY_STOP hoặc lệnh huỷ đợt.", False
        allowed, state = self.breakers.allow(spec.provider)
        if not allowed:
            return False, (f"Breaker {spec.provider} đang OPEN ({state.reason}), "
                           f"mở lại lúc {state.reopen_at or 'khi người vận hành reset'}."), True
        free_gb = shutil.disk_usage(self.paths.data_dir).free / 1e9
        if free_gb < float(self.cfg["wave"]["min_free_gb"]):
            return False, f"Đĩa còn {free_gb:.1f} GB < {self.cfg['wave']['min_free_gb']} GB.", False
        ok, reason = self.db_probe()
        if not ok:
            return False, f"DB vận hành không ghi được: {reason}", False
        res = self._run(spec, "preflight", "--check-prefix", parent=parent)
        if not res.ok:
            return False, "Prefix lệch danh mục: chạy build_article_prefix.py.", False
        return True, "", False

    def prepare(self, spec: WaveSpec) -> int:
        """Đóng gói đợt rồi giữ chỗ cho tập bài của nó; bỏ qua khi manifest đã có.

        Bộ đóng gói bỏ qua bài đang thuộc đợt khác chưa xong và bài đã hết lượt thử.
        Sau khi đóng gói, tập bài của đợt được ghi vào `ops_wave_articles`, nên đợt
        PARKED hay FAILED vẫn giữ bài của nó cho tới khi chạy lại xong hoặc bị huỷ.

        Args:
            spec: Thông số đợt.

        Returns:
            Số bài của đợt; 0 khi không có việc; -1 khi lỗi.
        """
        with tracing.span("prepare", "step", "article-packer", tracer=self._tracer(spec),
                          span_id=self._step_id(spec, "prepare"),
                          entrypoint="article_run.py → article_pack.py") as sp:
            n = self._prepare_impl(spec, sp.id)
            sp.set(articles=n)
            if n < 0:
                sp.status = "fail"
            elif n == 0:
                sp.status = "skipped"
            return n

    def _prepare_impl(self, spec: WaveSpec, parent: str | None) -> int:
        m = self.manifest(spec.wave_id)
        if m is None:
            w = self.cfg["wave"]
            exclude = self.store.excluded_article_ids(int(w["max_attempts_per_article"]))
            excl_path = self._log(spec, "prepare").with_name("exclude.txt")
            excl_path.parent.mkdir(parents=True, exist_ok=True)
            excl_path.write_text("\n".join(sorted(exclude)), encoding="utf-8")
            res = self._run(spec, "prepare", "--wave", spec.wave_id, "--runner", spec.provider,
                            "--limit", str(w["limit"]), "--batch", str(w["batch"]),
                            "--date", spec.target_date, "--exclude-file", str(excl_path),
                            parent=parent)
            m = self.manifest(spec.wave_id)
            if m is None:
                # article_pack thoát 2 khi không còn bài nào thoả điều kiện: đó là
                # "không có việc", không phải lỗi đóng gói.
                return 0 if res.returncode == 2 else -1
        self.store.record_wave_articles(spec.wave_id, self.article_ids(spec.wave_id))
        n = int(m.get("articles") or 0)
        self.store.upsert_wave(spec.wave_id, status="PREPARED", n_articles=n)
        return n

    def article_ids(self, wave_id: str) -> list[str]:
        """Đọc định danh bài của đợt từ các bảng ánh xạ lô.

        Args:
            wave_id: Mã đợt.

        Returns:
            Danh sách định danh bài, không trùng.
        """
        ids: list[str] = []
        for p in sorted(self.task_dir.glob(f"article_{wave_id}_*.map.json")):
            try:
                index = json.loads(p.read_text(encoding="utf-8")).get("index") or {}
            except (OSError, ValueError):
                continue
            ids.extend(index.values())
        return list(dict.fromkeys(ids))

    def analyze(self, spec: WaveSpec, round_no: int) -> AnalyzeOutcome:
        """Chạy phân tích lần đầu, hoặc vá đúng phần thiếu khi đã có đầu ra.

        Args:
            spec: Thông số đợt.
            round_no: Số thứ tự vòng (0 là vòng đầu).

        Returns:
            AnalyzeOutcome.
        """
        received, total = self._coverage(spec.wave_id)
        if total and received >= total:
            return AnalyzeOutcome("skip", "ok", received, total, br.OK)
        mode = "repair" if self._has_outputs(spec.wave_id) else "analyze"
        if mode == "repair":
            self._count_repair_round(spec.wave_id)
        self.store.upsert_wave(spec.wave_id, status="REPAIRING" if mode == "repair"
                               else "ANALYZING")
        w = self.cfg["wave"]

        def progress() -> object:
            sig = self._output_signature(spec.wave_id)
            if sig != getattr(progress, "last", None):
                progress.last = sig  # type: ignore[attr-defined]
                self.store.upsert_wave(spec.wave_id, progress_at=iso())
            return sig

        args = ["--wave", spec.wave_id, "--runner", spec.provider,
                "--concurrency", str(w["concurrency"]),
                "--repair" if mode == "repair" else "--analyze"]
        step = "analyze" if mode == "analyze" else f"repair{round_no}"
        tr = self._tracer(spec)
        sid = tr.begin(step, "step", "article-processor", span_id=self._step_id(spec, step),
                       mode=mode, round=round_no,
                       entrypoint=f"article_run.py --{'repair' if mode == 'repair' else 'analyze'}")
        res = self.executor(python_cmd(SCRIPTS / "article_run.py", *args), cwd=PROJECT_ROOT,
                            log_path=self._log(spec, step),
                            deadline_s=self._deadline("analyze" if mode == "analyze" else "repair"),
                            progress_fn=progress,
                            silence_s=float(w["progress_silence_minutes"]) * 60,
                            stop_fn=lambda: self.stop_requested(spec.wave_id),
                            extra_env=tr.child_env(sid))
        classes: list[str] = []
        batches: list[list[Any]] = []
        for batch_id, status, items, error in parse_batch_lines(res.tail):
            cls = br.classify_batch(status, error)
            classes.append(cls)
            batches.append([batch_id, status, items, cls])
            self._record_breaker(spec, cls, f"{batch_id}: {status} {error}"[:300])
            self.store.emit("batch.done", f"{batch_id}: {status} ({items} bài)",
                            level="info" if cls == br.OK else "warn", actor="runner",
                            wave_id=spec.wave_id, step=step,
                            data={"status": status, "class": cls, "error": error[:300]})
        if res.outcome in ("timeout", "stalled"):
            classes.append(br.TIMEOUT)
            self._record_breaker(spec, br.TIMEOUT, f"bước {step} {res.outcome}")
        elif not res.ok and not batches and res.outcome != "cancelled":
            cls = br.classify(res.tail)
            classes.append(cls)
            self._record_breaker(spec, cls, res.tail[-300:])
        self.store.emit("step.done" if res.ok else "step.failed",
                        f"{spec.wave_id}: {step} → {res.outcome} ({res.duration_s:.0f}s)",
                        level="info" if res.ok else "warn", actor="wave",
                        wave_id=spec.wave_id, step=step,
                        data={"rc": res.returncode, "outcome": res.outcome})
        received, total = self._coverage(spec.wave_id)
        tr.finish(sid, "ok" if res.ok else {"timeout": "timeout", "stalled": "timeout",
                                             "cancelled": "cancelled"}.get(res.outcome, "fail"),
                  rc=res.returncode, outcome=res.outcome, received=received, total=total,
                  worst=br.worst(classes), batches=len(batches))
        return AnalyzeOutcome(mode, res.outcome, received, total, br.worst(classes), batches)

    def _record_breaker(self, spec: WaveSpec, cls: str, detail: str) -> None:
        change = self.breakers.record(spec.provider, cls)
        if change == "opened":
            st = self.breakers.get(spec.provider)
            text = breaker_alert_text(spec.provider, st, detail)
            sev = "critical" if cls == br.AUTH else ("warn" if cls == br.QUOTA else "error")
            self.store.emit("breaker.opened", text, level="error", actor="daemon",
                            wave_id=spec.wave_id, data={"provider": spec.provider, "class": cls})
            buttons = [[("Chẩn đoán", f"/diagnose {spec.wave_id}"),
                        (f"Reset {spec.provider}", f"/reset {spec.provider}")]]
            impact, action = BREAKER_ACTION.get(cls, ("đợt tạm dừng", "xem nhật ký"))
            self.store.alert(sev, alert_card(sev, breaker_head(spec.provider, st), impact, action,
                                             f"/log 10 {spec.wave_id}"),
                             dedup_key=f"breaker:{spec.provider}:{cls}", buttons=buttons)
        elif change == "closed":
            self.store.emit("breaker.closed", f"{spec.provider}: kết nối lại bình thường",
                            actor="daemon", wave_id=spec.wave_id)
            self.store.alert("info", f"{spec.provider}: đã kết nối lại, breaker đóng.",
                             dedup_key=f"breaker:{spec.provider}:closed")

    def finish(self, spec: WaveSpec) -> StepResult:
        """Bung, nạp qua cổng DoD và hậu kiểm độ phủ.

        Args:
            spec: Thông số đợt.

        Returns:
            StepResult của `--finish`.
        """
        self.store.upsert_wave(spec.wave_id, status="FINISHING")
        with tracing.span("finish", "step", "article-expander", tracer=self._tracer(spec),
                          span_id=self._step_id(spec, "finish"),
                          entrypoint="article_run.py --finish") as sp:
            # Bước nạp DB không nhận lệnh dừng giữa chừng: AGY_STOP và /cancel chỉ có hiệu
            # lực ở ranh giới bước. Chỉ deadline (dành cho trường hợp treo thật) mới kill.
            res = self._run(spec, "finish", "--wave", spec.wave_id, "--runner", spec.provider,
                            "--finish", interruptible=False, parent=sp.id)
            sp.set(rc=res.returncode, outcome=res.outcome)
            if not res.ok:
                sp.status = "timeout" if res.outcome in ("timeout", "stalled") else "fail"
            return res

    def _deliver(self, spec: WaveSpec) -> bool:
        """Xuất xlsx giao hàng cho ngày của đợt, best-effort sau DONE.

        Writer có Idempotency Guard và checkpoint nên gọi lại an toàn.
        Lỗi giao hàng không lật trạng thái đợt (DB đã xong).

        Args:
            spec: Thông số đợt.

        Returns:
            True khi tiến trình giao hàng thoát 0.
        """
        self.store.upsert_wave(spec.wave_id, step="deliver")
        self.store.emit("step.started", f"{spec.wave_id}: bắt đầu deliver",
                        actor="wave", wave_id=spec.wave_id, step="deliver")
        with tracing.span("deliver", "step", "delivery-writer", tracer=self._tracer(spec),
                          span_id=self._step_id(spec, "deliver"),
                          entrypoint="write_user_output.py --date") as sp:
            res = self.executor(
                python_cmd(SCRIPTS / "write_user_output.py", "--date", spec.target_date),
                cwd=PROJECT_ROOT, log_path=self._log(spec, "deliver"),
                deadline_s=self._deadline("deliver"), stop_fn=None,
                extra_env=self._tracer(spec).child_env(sp.id))
            sp.set(rc=res.returncode, outcome=res.outcome)
            if not res.ok:
                sp.status = "timeout" if res.outcome in ("timeout", "stalled") else "fail"
            level = "info" if res.ok else "warn"
            self.store.emit("step.done" if res.ok else "step.failed",
                            f"{spec.wave_id}: deliver → {res.outcome} ({res.duration_s:.0f}s)",
                            level=level, actor="wave", wave_id=spec.wave_id, step="deliver",
                            data={"rc": res.returncode, "outcome": res.outcome,
                                  "tail": res.tail[-1500:] if not res.ok else None})
            return res.ok

    def finalize(self, spec: WaveSpec, status: str, reason: str, *,
                 resume_on_breaker: bool = False, counts_as_failure: bool = False,
                 summary: dict | None = None, clean: bool = True) -> str:
        """Chốt trạng thái cuối, cảnh báo và cập nhật chuỗi đợt sạch/hỏng.

        Chuỗi sạch chỉ tăng khi đợt DONE có bài thật (`clean`). Mọi kết cục khác đưa
        chuỗi sạch về 0.

        Args:
            spec: Thông số đợt.
            status: DONE, FAILED, PARKED hoặc CANCELLED.
            reason: Lý do.
            resume_on_breaker: Đợt PARKED sẽ tự chạy tiếp khi breaker cho phép.
            counts_as_failure: Tính vào chuỗi hỏng để tự hạ mức.
            summary: Số liệu đính kèm.
            clean: False với đợt DONE không có bài nào.

        Returns:
            Trạng thái cuối.
        """
        self.store.upsert_wave(spec.wave_id, status=status, reason=reason[:500],
                               finished_at=iso(), resume_on_breaker=int(resume_on_breaker))
        tr = self._tracer(spec)
        tr.close_running()
        tr.finish(self._root_id(spec), {"DONE": "ok", "FAILED": "fail", "PARKED": "parked",
                                        "CANCELLED": "cancelled"}.get(status, "fail"),
                  reason=reason[:300], final_status=status)
        try:
            wave_metrics.record_wave(self.paths, self.store, spec.wave_id, status)
        except Exception as exc:  # noqa: BLE001 — KPI hỏng không được làm hỏng việc chốt đợt
            self.store.emit("metrics.error", f"{spec.wave_id}: {exc}", level="warn",
                            actor="daemon", wave_id=spec.wave_id)
        self.store.set_state(f"cancel:{spec.wave_id}", None)
        level = {"DONE": "info", "CANCELLED": "warn", "PARKED": "warn"}.get(status, "error")
        self.store.emit(f"wave.{status.lower()}", f"{spec.wave_id}: {status} — {reason}",
                        level=level, actor="wave", wave_id=spec.wave_id, data=summary)
        if status == "DONE":
            self.store.set_state("fail_streak", "0")
            if not clean:
                return status
            streak_clean = int(self.store.get_state("clean_streak", "0") or 0) + 1
            self.store.set_state("clean_streak", str(streak_clean))
            try:
                delivered = self._deliver(spec)
            except Exception as exc:  # noqa: BLE001 — giao hàng hỏng không được lật DONE
                delivered = False
                self.store.emit("wave.deliver_failed", f"{spec.wave_id}: {exc}"[:300],
                                level="warn", actor="wave", wave_id=spec.wave_id)
            if delivered:
                self.store.emit("wave.delivered",
                                f"{spec.wave_id}: đã giao xlsx ngày {spec.target_date}",
                                actor="wave", wave_id=spec.wave_id)
            else:
                self.store.emit("wave.deliver_failed",
                                f"{spec.wave_id}: giao xlsx ngày {spec.target_date} thất bại, "
                                f"chạy tay write_user_output.py --date {spec.target_date}",
                                level="warn", actor="wave", wave_id=spec.wave_id)
                self.store.alert("warn", alert_card(
                    "warn", f"Đợt {spec.wave_id} đã nạp DB nhưng giao hàng thất bại.",
                    "người dùng chưa nhận được xlsx ngày "
                    f"{spec.target_date}",
                    f"chạy write_user_output.py --date {spec.target_date}",
                    f"/log 10 {spec.wave_id}"),
                    dedup_key=f"deliver:{spec.wave_id}")
            # Đợt bình thường đi vào bản tin; tin riêng chỉ khi cấu hình bật.
            if self.cfg["alerts"].get("push_wave_info"):
                self.store.alert("info", f"Đợt {spec.wave_id} ({spec.target_date}) xong: {reason}",
                                 dedup_key=None)
            return status
        self.store.set_state("clean_streak", "0")
        if counts_as_failure:
            minutes = int(self.cfg["wave"].get("cooldown_minutes", 0) or 0)
            if minutes > 0:
                self.store.set_state("cooldown_until", iso(now_vn() + timedelta(minutes=minutes)))
            streak = int(self.store.get_state("fail_streak", "0") or 0) + 1
            self.store.set_state("fail_streak", str(streak))
            limit = int(self.cfg["autonomy"]["demote_after_failures"])
            if streak >= limit:
                order = load_order(self.paths.standing_order)
                if order.exists and order.level != "L0":
                    old = order.level
                    order.level = demote(old)
                    order.created_by = "daemon:auto-demote"
                    save_order(self.paths.standing_order, order)
                    self.store.set_state("fail_streak", "0")
                    self.store.emit("autonomy.demoted", f"Tự hạ mức {old} → {order.level} "
                                    f"sau {streak} đợt hỏng liên tiếp.", level="critical")
                    self.store.alert("critical", alert_card(
                        "critical", f"Tự hạ mức {old} về {order.level} sau {streak} đợt hỏng "
                        f"liên tiếp. Lỗi cuối: {reason[:120]}",
                        "daemon không còn tự mở đợt",
                        f"chẩn đoán nguyên nhân rồi cấp lại bằng /level {old}",
                        f"/diagnose {spec.wave_id}"),
                                     buttons=[[("Chẩn đoán", f"/diagnose {spec.wave_id}")]])
        sev = "error" if status == "FAILED" else "warn"
        buttons = [[("Chạy lại", f"/retry {spec.wave_id}"),
                    ("Chẩn đoán", f"/diagnose {spec.wave_id}")]]
        if status != "CANCELLED":
            self.store.alert(sev, alert_card(
                sev, f"Đợt {spec.wave_id}: {label(WAVE_STATUS, status).lower()}. {reason[:160]}",
                "bài của đợt vẫn được giữ chỗ cho tới khi chạy lại hoặc huỷ",
                "bấm Chẩn đoán, rồi Chạy lại hoặc /cancel để nhả bài", f"/log 10 {spec.wave_id}"),
                             dedup_key=f"wave:{spec.wave_id}:{status}", buttons=buttons)
        return status


# Ảnh hưởng và việc cần làm theo lớp lỗi khi breaker mở.
BREAKER_ACTION = {
    br.AUTH: ("đợt dừng cho tới khi đăng nhập lại, bài vẫn được giữ chỗ",
              "mở terminal, đăng nhập lại agy rồi bấm Reset"),
    br.QUOTA: ("đợt tạm dừng tới giờ mở lại hạn mức",
               "chờ tự thử lại, hoặc chuyển provider bằng /provider openrouter"),
    br.NETWORK: ("đợt tạm dừng, daemon tự thử lại", "kiểm kết nối mạng"),
    br.TIMEOUT: ("đợt tạm dừng, daemon tự thử lại", "kiểm provider có đang chậm không"),
    br.EMPTY: ("đợt tạm dừng, daemon tự thử lại", "bấm Chẩn đoán để xem đầu ra rỗng"),
}


def breaker_head(provider: str, st: br.BreakerState) -> str:
    """Soạn câu sự việc khi breaker mở.

    Args:
        provider: Tên provider.
        st: Trạng thái breaker.

    Returns:
        Một câu mô tả sự việc.
    """
    return {
        br.AUTH: f"{provider} mất phiên đăng nhập",
        br.QUOTA: f"{provider} hết hạn mức, tự thử lại lúc {fmt_datetime(st.reopen_at)}",
        br.NETWORK: f"Mất kết nối tới {provider}, tự thử lại lúc {fmt_datetime(st.reopen_at)}",
        br.TIMEOUT: f"{provider} liên tục quá hạn, tự thử lại lúc {fmt_datetime(st.reopen_at)}",
        br.EMPTY: f"{provider} trả về rỗng nhiều lần, tự thử lại lúc {fmt_datetime(st.reopen_at)}",
    }.get(st.reason or "", f"Breaker {provider} mở ({label(FAILURE_CLASS, st.reason)})")


def breaker_alert_text(provider: str, st: br.BreakerState, detail: str) -> str:
    """Soạn nội dung sự kiện khi breaker mở, kèm chi tiết lỗi.

    Args:
        provider: Tên provider.
        st: Trạng thái breaker.
        detail: Chi tiết lỗi.

    Returns:
        Văn bản sự kiện.
    """
    head = {
        br.AUTH: f"{provider} mất phiên đăng nhập. Mở terminal và đăng nhập lại agy, "
                 f"rồi bấm Reset.",
        br.QUOTA: f"{provider} hết hạn mức (429). Tự thử lại lúc {st.reopen_at}.",
        br.NETWORK: f"Mất kết nối tới {provider}. Tự thử lại lúc {st.reopen_at}.",
        br.TIMEOUT: f"{provider} liên tục quá hạn. Tự thử lại lúc {st.reopen_at}.",
        br.EMPTY: f"{provider} trả về rỗng nhiều lần. Tự thử lại lúc {st.reopen_at}.",
    }.get(st.reason or "", f"Breaker {provider} mở ({st.reason}).")
    return f"{head}\nChi tiết: {detail}"


def _default_db_probe() -> tuple[bool, str]:
    from src.db.preflight import probe_write

    p = probe_write()
    return p.ok, p.reason


def l1_full_gold_short(wave_id: str) -> bool:
    """Đợt hỏng có đáng miễn khỏi chuỗi hỏng để tự hạ mức không.

    Miễn khi lớp nhận diện đã đủ 100% số bài của đợt: mô hình chạy, bung và nạp
    đều xong; phần thiếu chỉ còn ở lớp nội dung (bài mỏng theo ADR 0018 hoặc
    trượt DoD nội dung). Lỗi này không phản ánh sức khoẻ provider nên không được
    góp vào `fail_streak` làm daemon hạ mức.

    Args:
        wave_id: Mã đợt vừa FAILED ở bước finish.

    Returns:
        True khi L1 đủ và Gold thiếu; False trong mọi trường hợp khác (kể cả lỗi
        đọc DB — thiếu dữ kiện thì giữ hành vi cũ).
    """
    try:
        import sqlite3

        from scripts import article_run as ar
        from src.db.preflight import resolve_db_path

        ids = ar.wave_article_ids(wave_id)
        if not ids:
            return False
        conn = sqlite3.connect(f"file:{resolve_db_path().as_posix()}?mode=ro",
                               uri=True, timeout=10)
        try:
            cov = ar.coverage_of(conn, ids)
        finally:
            conn.close()
        return len(cov["l1_ok"]) == len(ids) and len(cov["gold_ok"]) < len(ids)
    except Exception:
        return False


class WaveOps(Protocol):
    """Giao diện các bước mà `drive_wave` gọi; bản DBOS bọc mỗi bước thành step bền."""

    def preflight(self, spec: dict) -> list: ...
    def prepare(self, spec: dict) -> int: ...
    def analyze(self, spec: dict, round_no: int) -> dict: ...
    def stop_requested(self, spec: dict) -> bool: ...
    def finish(self, spec: dict) -> list: ...
    def finalize(self, spec: dict, status: str, reason: str, flags: dict) -> str: ...


def drive_wave(spec_d: dict, ops: WaveOps, cfg: dict) -> str:
    """Chạy trọn vòng đời một đợt theo máy trạng thái của ADR 0012 (sửa đổi 2026-10-01).

    Đợt đã mở thì chạy tới nạp DB mà không hỏi người: chốt kỹ thuật của `--finish`
    (độ phủ ≥ 90% ở cả hai lớp) quyết việc nạp, theo amendment ADR 0008. Người điều
    khiển bằng standing order, `/pause` và `/stop`. Giao hàng chạy best-effort sau
    DONE cho ngày của đợt; lỗi giao hàng không lật DONE.

    Hàm chỉ chứa logic tất định; mọi tác dụng phụ đi qua `ops`, nên khi chạy trong
    workflow DBOS mỗi lời gọi được checkpoint và không lặp lại sau khi khôi phục.

    Args:
        spec_d: WaveSpec dạng từ điển.
        ops: Bộ bước.
        cfg: Cấu hình đầy đủ.

    Returns:
        Trạng thái cuối của đợt.
    """
    ok, reason, breaker_wait = ops.preflight(spec_d)
    if not ok:
        return ops.finalize(spec_d, "PARKED", reason,
                            {"resume_on_breaker": breaker_wait, "failure": False})
    n = ops.prepare(spec_d)
    if n < 0:
        return ops.finalize(spec_d, "FAILED", "Đóng gói đợt thất bại.", {"failure": True})
    if n == 0:
        return ops.finalize(spec_d, "DONE", "Không còn bài để xử lý.",
                            {"failure": False, "clean": False})

    out: dict = {}
    for round_no in range(1 + int(cfg["wave"]["max_repair_rounds"])):
        out = ops.analyze(spec_d, round_no)
        if out["received"] >= out["total"] > 0:
            break
        if out["step_outcome"] == "cancelled":
            return ops.finalize(spec_d, "CANCELLED", "Người vận hành dừng đợt.",
                                {"failure": False})
        if out["worst"] in (br.AUTH, br.QUOTA, br.NETWORK):
            break
    total = max(1, out.get("total", 0))
    coverage = out.get("received", 0) / total
    if coverage < MIN_COVERAGE:
        provider_issue = out.get("worst") in br.PROVIDER_CLASSES
        return ops.finalize(
            spec_d, "PARKED",
            f"Độ phủ phân tích {coverage:.0%} < {MIN_COVERAGE:.0%} (lỗi {out.get('worst')}).",
            {"resume_on_breaker": provider_issue, "failure": not provider_issue,
             "summary": out})

    if ops.stop_requested(spec_d):
        return ops.finalize(spec_d, "CANCELLED", "Người vận hành dừng đợt trước bước nạp DB.",
                            {"failure": False, "summary": out})
    fin = ops.finish(spec_d)
    if not fin[0]:
        failure = True
        suffix = ""
        if l1_full_gold_short(spec_d["wave_id"]):
            failure = False
            suffix = " (L1 đủ 100%, Gold thiếu không tính vào chuỗi hỏng theo ADR 0018)"
        return ops.finalize(spec_d, "FAILED", f"--finish không đạt cổng kỹ thuật "
                            f"({fin[1]}). {fin[2][-300:]}{suffix}", {"failure": failure})
    return ops.finalize(spec_d, "DONE",
                        f"{out.get('received')}/{out.get('total')} bài phân tích, đã nạp DB.",
                        {"failure": False, "summary": out})


class DirectOps:
    """Bộ bước gọi thẳng WaveSteps, dùng cho kiểm thử và chạy không DBOS.

    Attributes:
        steps: WaveSteps.
    """

    def __init__(self, steps: WaveSteps) -> None:
        """Gắn bộ bước.

        Args:
            steps: WaveSteps.
        """
        self.steps = steps

    def preflight(self, spec: dict) -> list:
        return list(self.steps.preflight(WaveSpec(**spec)))

    def prepare(self, spec: dict) -> int:
        return self.steps.prepare(WaveSpec(**spec))

    def analyze(self, spec: dict, round_no: int) -> dict:
        return asdict(self.steps.analyze(WaveSpec(**spec), round_no))

    def stop_requested(self, spec: dict) -> bool:
        return self.steps.stop_requested(spec["wave_id"])

    def finish(self, spec: dict) -> list:
        r = self.steps.finish(WaveSpec(**spec))
        return [r.ok, r.outcome, r.tail]

    def finalize(self, spec: dict, status: str, reason: str, flags: dict) -> str:
        return self.steps.finalize(WaveSpec(**spec), status, reason,
                                   resume_on_breaker=bool(flags.get("resume_on_breaker")),
                                   counts_as_failure=bool(flags.get("failure")),
                                   summary=flags.get("summary"),
                                   clean=bool(flags.get("clean", True)))
