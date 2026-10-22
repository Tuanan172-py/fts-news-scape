"""Call the on-duty `ops-sentinel` agent through agy to diagnose incidents and propose one command."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.ops.breakers import Breakers
from src.ops.procrun import CREATE_NO_WINDOW, read_tail
from src.core.redact import redact
from src.ops.store import OpsStore

SENTINEL_TIMEOUT_S = 240

# The only commands sentinel may propose; `<wave>` and `<provider>` are placeholders.
WHITELIST = (
    "/retry <wave>", "/resume", "/pause", "/run", "/reset <provider>",
    "/provider openrouter", "/provider agy", "/capture restart", "none",
)
_ALLOWED = re.compile(
    r"^(/retry W[\w-]+|/resume|/pause|/run|/reset (agy|openrouter)|"
    r"/provider (agy|openrouter)|/capture restart|none)$")

PERSONA = """Bạn là ops-sentinel, trực ban vận hành của pipeline tin tức News-Scape.

Nhiệm vụ: đọc trích đoạn sự kiện vận hành, trạng thái breaker và đuôi nhật ký của một đợt
phân tích bài báo, rồi chẩn đoán nguyên nhân và đề xuất đúng MỘT lệnh để người vận hành bấm.

Bối cảnh hệ thống:
- Daemon Python điều phối đợt: preflight → prepare → analyze/repair → finish (nạp DB).
- Runner agy gọi mô hình một lượt cho mỗi lô; OpenRouter là provider dự phòng.
- Breaker theo provider: AUTH (mất đăng nhập), QUOTA (429), NETWORK, TIMEOUT, EMPTY.
- Cổng `--finish` đòi độ phủ ≥ 90% ở cả hai lớp nhận diện và nội dung.

Lệnh được phép đề xuất (chọn đúng một, giữ nguyên cú pháp):
/retry <mã đợt> · /resume · /pause · /run · /reset agy · /reset openrouter ·
/provider openrouter · /provider agy · /capture restart · none

Không được tự thi hành gì; không bịa dữ kiện ngoài trích đoạn. Thiếu dữ kiện thì nói rõ
và đề xuất none."""

GUARD = """

## QUY TẮC BẮT BUỘC:
- Không gọi bất kỳ công cụ nào.
- Trả về DUY NHẤT một đối tượng JSON:
  {"chan_doan": "...", "nguyen_nhan": ["..."], "lenh_de_xuat": "...", "ly_do": "..."}
"""


@dataclass
class Diagnosis:
    """Validated diagnosis result.

    Attributes:
        summary: Short diagnosis.
        causes: Possible causes.
        command: Proposed command from the allow-list, or `none`.
        rationale: Reason the command was chosen.
        raw: Original model text.
    """

    summary: str
    causes: list[str]
    command: str
    rationale: str
    raw: str = ""


def build_context(store: OpsStore, breakers: Breakers, log_dir: Path,
                  wave_id: str | None) -> str:
    """Collect operations excerpts as input for sentinel.

    Args:
        store: Operations store.
        breakers: Per-provider breakers.
        log_dir: The `ops_logs` directory.
        wave_id: Wave to diagnose; None uses the general context.

    Returns:
        Context text, limited to about 12 thousand characters.
    """
    parts: list[str] = []
    if wave_id:
        w = store.wave(wave_id)
        if w:
            parts.append("## Đợt\n" + json.dumps(dict(w), ensure_ascii=False))
    lines = [f"{b.provider}: {b.state} lớp={b.last_class} lỗi_liên_tiếp={b.consecutive_failures} "
             f"mở_lại={b.reopen_at}" for b in breakers.all()]
    parts.append("## Breaker\n" + ("\n".join(lines) or "(chưa có)"))
    evs = store.events(limit=40, wave_id=wave_id)
    parts.append("## Sự kiện gần nhất\n" + "\n".join(
        f"{e['ts']} {e['level']} {e['kind']} {e['message']}" for e in evs))
    if wave_id:
        wdir = log_dir / "waves" / wave_id
        for p in sorted(wdir.glob("*.log"), key=lambda x: x.stat().st_mtime)[-2:]:
            parts.append(f"## Đuôi nhật ký {p.name}\n" + read_tail(p, 30))
    text = redact("\n\n".join(parts)) or ""
    return text[-12000:]


def parse_diagnosis(text: str, wave_id: str | None) -> Diagnosis:
    """Extract the sentinel JSON object and constrain the command to the allow-list.

    Args:
        text: Text returned by the model.
        wave_id: Wave being diagnosed, used to validate the `/retry` command.

    Returns:
        The Diagnosis; a command outside the allow-list is replaced by `none`.
    """
    obj: dict = {}
    m = re.search(r"\{.*\}", text or "", re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            obj = {}
    cmd = str(obj.get("lenh_de_xuat") or "none").strip()
    if not _ALLOWED.match(cmd):
        cmd = "none"
    if cmd.startswith("/retry") and wave_id and cmd != f"/retry {wave_id}":
        cmd = "none"
    causes = obj.get("nguyen_nhan") or []
    if not isinstance(causes, list):
        causes = [str(causes)]
    return Diagnosis(summary=str(obj.get("chan_doan") or "Không đọc được chẩn đoán."),
                     causes=[str(c) for c in causes][:5], command=cmd,
                     rationale=str(obj.get("ly_do") or ""), raw=(text or "")[:2000])


def call_agy(prompt: str, *, timeout_s: int = SENTINEL_TIMEOUT_S) -> str:
    """Call agy once with the `ops-sentinel` agent in an isolated profile without tools.

    Args:
        prompt: Operations context.
        timeout_s: Time limit.

    Returns:
        Response text of the model.

    Raises:
        RuntimeError: If agy fails, times out or returns an empty response.
    """
    from src.agent.agy_runner import DEFAULT_MODEL, build_sandbox_profile, resolve_agy

    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    profile = local / "news-scape" / "agy_profiles" / "ops-sentinel"
    work = local / "news-scape" / "agy_work" / "ops-sentinel"
    work.mkdir(parents=True, exist_ok=True)
    build_sandbox_profile(profile, PERSONA, work_dir=work, agent_name="ops-sentinel",
                          description="Trực ban vận hành, chẩn đoán sự cố pipeline",
                          instruction_guard=GUARD)
    env = os.environ.copy()
    env.update({"USERPROFILE": str(profile), "HOME": str(profile), "PYTHONUTF8": "1",
                "ANTIGRAVITY_APP_DATA_DIR": str(profile / ".gemini" / "antigravity-cli")})
    cmd = [resolve_agy(), "-p=", "--agent", "ops-sentinel", "--model", DEFAULT_MODEL,
           "--input-format", "stream-json", "--output-format", "stream-json",
           f"--print-timeout={timeout_s}s", "--disable-slash-commands"]
    payload = json.dumps({"event": "user", "message": {"content": prompt}},
                         ensure_ascii=False) + "\n"
    try:
        proc = subprocess.run(cmd, input=payload, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", cwd=str(work), env=env,
                              timeout=timeout_s + 30,
                              creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"agy quá hạn {timeout_s}s") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"agy thoát {proc.returncode}: {(proc.stderr or '')[:300]}")
    response = ""
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (ev.get("type") or ev.get("event")) == "result":
            res = ev.get("result") or ev.get("data") or ev
            response = res.get("response") or res.get("content") or ""
    if not response.strip():
        raise RuntimeError("agy trả về rỗng")
    return response


def diagnose(store: OpsStore, breakers: Breakers, log_dir: Path, wave_id: str | None, *,
             call: Callable[[str], str] = call_agy) -> Diagnosis:
    """Diagnose and record the result as an event; execute nothing.

    Args:
        store: Operations store.
        breakers: Per-provider breakers.
        log_dir: The `ops_logs` directory.
        wave_id: Wave to diagnose.
        call: Function that calls the model; replaceable in tests.

    Returns:
        The Diagnosis.
    """
    ctx = build_context(store, breakers, log_dir, wave_id)
    try:
        d = parse_diagnosis(call(ctx), wave_id)
    except Exception as exc:  # noqa: BLE001 — a sentinel failure must not break the daemon
        d = Diagnosis(summary=f"Sentinel không chạy được: {exc}", causes=[], command="none",
                      rationale="Chẩn đoán thủ công bằng /log và pipeline_radar.py status.")
    store.emit("sentinel.diagnosis", d.summary, actor="sentinel", wave_id=wave_id,
               data={"causes": d.causes, "command": d.command, "rationale": d.rationale})
    return d
