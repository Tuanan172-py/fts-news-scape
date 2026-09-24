"""Bộ điều phối lập lịch và thực thi các chu kỳ xử lý pipeline ban ngày."""

from __future__ import annotations

import signal
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Đảm bảo project root luôn có trong sys.path khi chạy trực tiếp `python morninger.py`
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

_SCRIPTS_DIR = Path(_project_root) / "scripts"

from loguru import logger

from src.core.config import load_settings
from src.core.logging import setup_logging
from src.core.models import VN_TZ
from src.core.proclock import SCHEDULER_LOCK_STALE_SECONDS, capture_lock, lock_owner
from src.db.store import ArticleStore
from src.pipeline.derive import rederive_incremental
from src.pipeline.drift import list_drift
from src.orchestrator import Orchestrator


def _force_utf8_stdio() -> None:
    """Cấu hình lại luồng xuất nhập chuẩn sang UTF-8 tránh lỗi mã hóa ký tự."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def build_scheduler(capture_fn, derive_fn, drift_fn, cfg: dict, reclaim_fn=None):
    """Khởi tạo bộ lập lịch BlockingScheduler với các tác vụ định kỳ.

    Không có job định tuyến L1 code-first. Job ấy thuộc lane L1/Gold đã ngừng (ADR
    0010): nó ghi bản tra bảng vào `l1_outputs`, và bộ chọn bài cũ coi bản ấy là đã
    phân tích nên bỏ qua bài vĩnh viễn.

    Args:
        capture_fn: Hàm thực thi thu thập dữ liệu Bronze.
        derive_fn: Hàm thực thi bóc tách tăng dần Silver.
        drift_fn: Hàm kiểm tra sai lệch mẫu giao diện (drift).
        cfg: Từ điển cấu hình thời gian chạy của morninger.
        reclaim_fn: Hàm nhả gói công việc kẹt ở `claimed` quá hạn. None → không đăng ký.

    Returns:
        Đối tượng BlockingScheduler đã đăng ký đầy đủ các công việc.
    """
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    cap_interval = int(cfg.get("capture_interval_minutes", 15))
    rederive_interval = int(cfg.get("rederive_interval_minutes", 30))
    drift_hour = int(cfg.get("drift_hour", 6))
    drift_minute = int(cfg.get("drift_minute", 0))

    scheduler = BlockingScheduler()
    now = datetime.now(VN_TZ)
    scheduler.add_job(
        capture_fn,
        IntervalTrigger(minutes=cap_interval),
        id="capture",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=300,
        next_run_time=now,
    )
    # re-derive bắt đầu sau capture ~1 phút (head start), rồi đều đặn.
    scheduler.add_job(
        derive_fn,
        IntervalTrigger(minutes=rederive_interval),
        id="derive",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=300,
        next_run_time=now + timedelta(seconds=60),
    )
    scheduler.add_job(
        drift_fn,
        CronTrigger(hour=drift_hour, minute=drift_minute),
        id="drift",
        coalesce=True,
        max_instances=1,
    )
    if reclaim_fn is not None:
        # Không có worker nào claim thì cũng không ai nhả — phải có job riêng.
        scheduler.add_job(
            reclaim_fn,
            IntervalTrigger(minutes=int(cfg.get("reclaim_interval_minutes", 30))),
            id="reclaim",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=300,
            next_run_time=now + timedelta(seconds=120),
        )
    return scheduler


class Morninger:
    """Điều phối tiến trình lập lịch thu thập và tinh chỉnh tin tức ban ngày.

    Attributes:
        settings: Cấu hình hệ thống chung.
        store: Kho dữ liệu cơ sở ArticleStore.
        cfg: Cấu hình riêng của mô-đun morninger.
        orch: Đối tượng điều phối Orchestrator.
    """

    def __init__(self):
        """Khởi tạo đối tượng điều phối Morninger."""
        self.settings = load_settings()
        setup_logging(
            self.settings["logging"]["level"], self.settings["logging"]["dir"]
        )
        self.store = ArticleStore(self.settings["database"]["path"])
        self.cfg = self.settings.get("morninger", {})
        self.orch = Orchestrator()
        self._lock_owner = lock_owner()          # Fix F
        self._capture_lock = capture_lock()
        self._stopped = False

    # -- jobs -----------------------------------------------------------------
    def run_capture(self) -> int:
        """Thực thi chu kỳ thu thập dữ liệu nguồn Bronze, nối tiếp bù ngay các bài
        `detail_deferred` (vượt cap trong cycle) — giảm cửa sổ rủi ro nguồn xóa bài
        trước khi kịp lấy nội dung đầy đủ (đặc điểm tin VN).

        Returns:
            Số lượng bài viết mới được ghi nhận (chu kỳ capture chính).
        """
        n = self.orch.run_cycle()
        self.run_backfill_deferred()
        return n

    def run_backfill_deferred(self) -> int:
        """Gọi backfill_deferred.py ngay sau capture để bù nội dung đầy đủ cho bài bị
        hoãn (vượt `max_details_per_cycle`) VÀ bài fetch lỗi tạm thời (timeout/5xx).
        Không chặn cycle nếu lỗi.

        Returns:
            Exit code của tiến trình con, hoặc -1 nếu không chạy được.
        """
        limit = int(self.cfg.get("deferred_backfill_limit", 60))
        max_attempts = int(self.cfg.get("deferred_max_attempts", 5))
        window = int(self.cfg.get("deferred_retry_window_hours", 24))
        budget = int(self.cfg.get("deferred_budget_seconds", 90))
        script = _SCRIPTS_DIR / "maintenance" / "backfill_deferred.py"
        try:
            proc = subprocess.run(
                [sys.executable, str(script), "--fetch", "--limit", str(limit),
                 "--mode", "all", "--max-attempts", str(max_attempts),
                 "--retry-window-hours", str(window),
                 "--budget-seconds", str(budget)],
                # timeout phải NỚI HƠN budget để script kịp tự dừng sạch và báo cáo;
                # bị giết bởi timeout là mất trắng thống kê của lượt đó.
                # encoding PHẢI khai tường minh: script con phát UTF-8, thiếu dòng này thì
                # tiến trình cha giải mã theo cp1252, reader thread chết và stdout = None.
                cwd=_project_root, capture_output=True, text=True, timeout=budget + 60,
                encoding="utf-8", errors="replace",
            )
            if (proc.stdout or "").strip():
                logger.info("[morninger] backfill_deferred: {}",
                           proc.stdout.strip().splitlines()[-1])
            if proc.returncode != 0:
                logger.warning("[morninger] backfill_deferred exit={}: {}",
                               proc.returncode, proc.stderr[-500:])
            return proc.returncode
        except Exception as e:  # noqa: BLE001 — job phụ trợ, không được làm hỏng capture
            logger.error("[morninger] backfill_deferred lỗi (bỏ qua): {}", e)
            return -1

    def run_derive(self) -> dict:
        """Thực thi chu kỳ chuyển đổi tăng dần từ Bronze sang Silver.

        Returns:
            Từ điển báo cáo tiến độ xử lý và thông tin manifest nếu đạt điểm kiểm tra.
        """
        s = rederive_incremental(self.store)
        if s["checkpoint_reached"]:
            try:
                from src.export.silver_manifest import export_silver_manifest

                path, n = export_silver_manifest(self.store, today=True)
                s["manifest"] = str(path)
                s["manifest_count"] = n
                logger.info("[morninger] silver manifest: {} bài -> {}", n, path)
            except Exception as e:  # noqa: BLE001 — export là tiện ích
                logger.error("silver manifest export lỗi (bỏ qua): {}", e)
        return s

    def run_reclaim(self) -> int:
        """Nhả các gói công việc kẹt ở `claimed` quá hạn về `pending`.

        Trước đây `reclaim_stale()` chỉ chạy bên trong `Catalog.claim()`, nên khi không có
        worker nào đến nhận việc thì không ai nhả — hàng `claimed` treo vĩnh viễn (đo được
        304 hàng ngày 2026-09-17).

        Returns:
            Số gói công việc đã được hoàn trả hàng đợi.
        """
        try:
            from src.handoff.catalog import Catalog

            n = Catalog(self.store).reclaim_stale()
            if n:
                logger.info("[morninger] reclaim: nhả {} work_item kẹt ở 'claimed'", n)
            return n
        except Exception as e:  # noqa: BLE001 — job phụ trợ, không được làm hỏng scheduler
            logger.error("[morninger] reclaim lỗi (bỏ qua): {}", e)
            return -1

    def run_drift(self) -> int:
        """Kiểm tra và cảnh báo các bài viết gặp sai lệch mẫu hoặc bộ chọn.

        Returns:
            Số lượng bài viết có trạng thái sai lệch phát hiện được.
        """
        rows = list_drift(self.store, limit=int(self.cfg.get("drift_limit", 100)))
        if not rows:
            logger.info("[morninger] drift report: không có bài drift/broken ✅")
            return 0
        logger.warning("[morninger] drift report: {} bài cần reconcile", len(rows))
        for r in rows[:20]:
            logger.warning(
                "  {}  {}  {}  {}",
                r["state"],
                r["source_domain"] or "",
                r["captured_at"] or "",
                r["url_title_hash"][:16],
            )
        if len(rows) > 20:
            logger.warning("  ... (+{} more)", len(rows) - 20)
        return len(rows)

    # -- scheduler ------------------------------------------------------------
    def acquire_capture_lock(self) -> bool:
        """Chiếm khoá tệp dùng chung của mọi tiến trình cào tin trên máy.

        Returns:
            True khi chiếm được, False khi tiến trình cào khác đang chạy.
        """
        if self._capture_lock.acquire():
            return True
        logger.error("Tiến trình cào tin khác đang chạy ({}), giữ khoá {}. Từ chối khởi "
                     "động để tránh cào song song.", self._capture_lock.holder() or "?",
                     self._capture_lock.path)
        return False

    def start_scheduler(self) -> bool:
        """Chiếm khoá cào tin rồi chạy bộ lập lịch đến khi nhận tín hiệu dừng.

        Returns:
            False khi tiến trình cào khác đang giữ khoá, True khi bộ lập lịch đã chạy và dừng.
        """
        if not self.acquire_capture_lock():
            return False
        # Fix F: chỉ 1 scheduler chạy. Chiếm lock; giao quyền heartbeat cho orchestrator
        # nội bộ (cùng pid) — run_capture→orch.run_cycle sẽ refresh lock mỗi cycle.
        if not self.store.try_acquire_lock("scheduler", self._lock_owner,
                                           SCHEDULER_LOCK_STALE_SECONDS):
            logger.error("Scheduler khác đang chạy (lock trong pipeline_state). "
                         "Từ chối khởi động morninger để tránh double-scrape.")
            self._capture_lock.release()
            return False
        self.orch._lock_owner = self._lock_owner
        self.orch._owns_scheduler_lock = True

        scheduler = build_scheduler(
            self.run_capture, self.run_derive, self.run_drift, self.cfg,
            self.run_reclaim,
        )

        def handle_signal(signum, frame):
            logger.warning("Signal {} — stopping morninger...", signum)
            scheduler.shutdown(wait=False)

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        cap = int(self.cfg.get("capture_interval_minutes", 15))
        rederive = int(self.cfg.get("rederive_interval_minutes", 30))
        drift_hour = int(self.cfg.get("drift_hour", 6))
        drift_minute = int(self.cfg.get("drift_minute", 0))
        reclaim = int(self.cfg.get("reclaim_interval_minutes", 30))
        logger.info(
            "Morninger started: capture/{}min (+backfill_deferred nối tiếp), "
            "derive/{}min, reclaim/{}min, drift/{}:{}",
            cap,
            rederive,
            reclaim,
            drift_hour,
            drift_minute,
        )
        try:
            scheduler.start()
        finally:
            self.shutdown()
        return True

    def shutdown(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        logger.info("Morninger shutdown — flushing orchestrator...")
        self.orch.shutdown()
        self._capture_lock.release()
        logger.info("Morninger shutdown complete.")


def main(argv: list[str]) -> int:
    _force_utf8_stdio()
    args = [a for a in argv if not a.startswith("--")]
    once = "--once" in argv
    m = Morninger()

    if once:
        sub = args[0] if args else "derive"
        try:
            if sub == "capture":
                if not m.acquire_capture_lock():
                    return 1
                print("🔄 [morninger] Đang thực thi Capture cycle...", flush=True)
                n = m.run_capture()
                print(f"✅ capture done: {n} new articles")
            elif sub == "derive":
                print("🔄 [morninger] Bắt đầu tiến trình Re-derive Silver từ Bronze...", flush=True)
                s = m.run_derive()
                print(
                    f"✅ derive done: processed={s['processed']} ok={s['ok']} "
                    f"held={s['held']} backlog={s['backlog']} "
                    f"checkpoint={s['checkpoint_reached']} "
                    f"watermark={s['watermark_new']}"
                )
                if s.get("manifest"):
                    print(f"manifest: {s['manifest_count']} bài -> {s['manifest']}")
            elif sub == "drift":
                n = m.run_drift()
                print(f"drift done: {n} bài cần reconcile")
            else:
                print(f"unknown --once target: {sub} (capture|derive|drift)")
                return 2
        finally:
            m.shutdown()
        return 0

    return 0 if m.start_scheduler() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
