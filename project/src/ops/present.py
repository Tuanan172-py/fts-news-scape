"""Provide the Vietnamese formatting and labels shared by Telegram messages and the Control Room."""

from __future__ import annotations

import math
import re

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _round(x: float) -> int:
    """Round half up, matching the browser `Math.round` convention."""
    return int(math.floor(x + 0.5))


# Alert levels: text labels, no icons.
LEVEL_LABEL = {"critical": "KHẨN", "error": "LỖI", "warn": "CẢNH BÁO", "info": "THÔNG TIN",
               "digest": "BẢN TIN"}

WAVE_STATUS = {
    "SENSED": "Mới mở", "PREFLIGHT": "Kiểm tra trước", "PREPARED": "Đã đóng gói",
    "ANALYZING": "Đang phân tích", "REPAIRING": "Đang vá", "ANALYZED": "Đã phân tích",
    "FINISHING": "Đang nạp DB", "DONE": "Xong", "FAILED": "Lỗi", "PARKED": "Tạm dừng",
    "CANCELLED": "Đã huỷ",
}

SPAN_STATUS = {
    "ok": "Xong", "running": "Đang chạy", "fail": "Lỗi", "timeout": "Quá hạn",
    "partial": "Một phần", "skipped": "Bỏ qua", "parked": "Tạm dừng",
    "cancelled": "Đã huỷ", "interrupted": "Bị ngắt",
}

SPAN_KIND = {"workflow": "Quy trình", "step": "Bước", "script": "Script", "agent": "Lô agy",
             "gate": "Cổng", "tool": "Công cụ", "human": "Người"}

NODE_STATE = {"ok": "Ổn", "run": "Đang chạy", "fail": "Lỗi", "idle": "Rảnh", "draft": "Draft"}

BREAKER_STATE = {"CLOSED": "Đóng", "OPEN": "Mở", "HALF_OPEN": "Thử lại"}

FAILURE_CLASS = {"AUTH": "Mất đăng nhập", "QUOTA": "Hết hạn mức", "NETWORK": "Mất mạng",
                 "TIMEOUT": "Quá hạn", "EMPTY": "Trả rỗng", "FATAL": "Lỗi nặng",
                 "VIOLATION": "Vi phạm công cụ", "OK": "Đạt"}

CAPTURE_MODE = {"child": "daemon giữ", "external": "chạy ngoài", "backoff": "đang chờ khởi động lại",
                "gave_up": "đã bỏ cuộc", "disabled": "tắt"}

PROPOSAL_STATUS = {"open": "Đang mở", "story_opened": "Đã mở story", "deferred": "Đã hoãn",
                   "rejected": "Đã bác"}

AGENT_STATUS = {"active": "Hoạt động", "draft": "Draft", "retired": "Đã gỡ"}

TRIGGER = {"T1": "Đủ khối lượng", "T2": "Bài chờ lâu", "T3": "Khung giờ chốt",
           "manual": "Người chạy", "retry": "Chạy lại", "backlog": "Chạy tay: bài tồn",
           "adhoc": "Chạy tay", "bench": "Chạy tay: thử nghiệm"}

# Table sent to the web page through `/api/labels`; every text label of the UI comes from here.
LABELS = {
    "level": LEVEL_LABEL, "wave_status": WAVE_STATUS, "span_status": SPAN_STATUS,
    "span_kind": SPAN_KIND, "node_state": NODE_STATE, "breaker_state": BREAKER_STATE,
    "failure_class": FAILURE_CLASS, "capture_mode": CAPTURE_MODE,
    "proposal_status": PROPOSAL_STATUS, "agent_status": AGENT_STATUS, "trigger": TRIGGER,
}


def label(table: dict[str, str], key: str | None) -> str:
    """Look up a Vietnamese label, returning the original key when no label exists.

    Args:
        table: Label table.
        key: Value to look up.

    Returns:
        The Vietnamese label, the original key, or a dash when there is no value.
    """
    if key is None or key == "":
        return "–"
    return table.get(str(key), str(key))


def fmt_int(value: float | int | None) -> str:
    """Format an integer in the vi-VN style, with a dot as the thousands separator.

    Args:
        value: Number to format.

    Returns:
        String such as `1.234`, or a dash when the value is missing.
    """
    if value is None:
        return "–"
    return f"{_round(value):,}".replace(",", ".")


def fmt_pct(ratio: float | None) -> str:
    """Format a ratio as a whole-number percentage.

    Args:
        ratio: Ratio between 0 and 1.

    Returns:
        String such as `56%`, or a dash when the value is missing.
    """
    if ratio is None:
        return "–"
    return f"{_round(ratio * 100)}%"


def fmt_duration(seconds: float | None) -> str:
    """Format a duration: ms below 1 s, one decimal below 10 s, whole seconds from 10 s, "ph" (minutes) from 60 s.

    Args:
        seconds: Number of seconds.

    Returns:
        String such as `66 ms`, `5,4 s`, `54 s`, `1 ph 54 s`.
    """
    if seconds is None:
        return "–"
    ms = _round(seconds * 1000)
    if ms < 1000:
        return f"{ms} ms"
    if seconds < 10:
        tenths = math.floor(seconds * 10 + 0.5) / 10
        if tenths < 10:
            return f"{tenths:.1f}".replace(".", ",") + " s"
    total = _round(seconds)
    if total < 60:
        return f"{total} s"
    return f"{total // 60} ph {total % 60} s"


def _is_iso(text: str) -> bool:
    """Report whether the string starts with a date in `yyyy-MM-dd` form."""
    return bool(_ISO_DATE.match(text))


def fmt_datetime(iso: str | None) -> str:
    """Format an ISO timestamp as `dd/MM HH:mm`, or `dd/MM` when only a date is present.

    Slices the string by position without converting time zones, to match the web page character for character.

    Args:
        iso: ISO 8601 string.

    Returns:
        String such as `01/10 14:34`; a dash when empty; the original string when not ISO.
    """
    if not iso:
        return "–"
    s = str(iso)
    if not _is_iso(s):
        return s
    day = f"{s[8:10]}/{s[5:7]}"
    return day if len(s) < 16 else f"{day} {s[11:16]}"


def fmt_time(iso: str | None) -> str:
    """Format an ISO timestamp as `HH:mm`.

    Args:
        iso: ISO 8601 string.

    Returns:
        String such as `14:34`; a dash when empty or date-only; the original string when not ISO.
    """
    if not iso:
        return "–"
    s = str(iso)
    if not _is_iso(s):
        return s
    return s[11:16] if len(s) >= 16 else "–"


def fmt_date(iso: str | None) -> str:
    """Format an ISO date as `dd/MM/yyyy`.

    Args:
        iso: ISO 8601 date or timestamp string.

    Returns:
        String such as `30/10/2026`; a dash when empty; the original string when not ISO.
    """
    if not iso:
        return "–"
    s = str(iso)
    if not _is_iso(s):
        return s
    return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"


def clip_lines(text: str, max_chars: int = 3800) -> str:
    """Truncate text at a line boundary, never mid-line.

    Args:
        text: Multi-line text.
        max_chars: Maximum number of characters (Telegram allows 4096).

    Returns:
        The original text if short enough, otherwise the leading lines plus a line reporting how many lines were dropped.
    """
    if len(text) <= max_chars:
        return text
    lines, used, kept = text.split("\n"), 0, []
    for ln in lines:
        if used + len(ln) + 1 > max_chars - 60:
            break
        kept.append(ln)
        used += len(ln) + 1
    return "\n".join(kept + [f"... còn {len(lines) - len(kept)} dòng (xem Phòng điều khiển)"])


def success_rate(ok: int, fail: int, partial: int = 0) -> float | None:
    """Compute the success rate of finished spans.

    Running and skipped spans are excluded. Partial spans count in the denominator but not
    as successes.

    Args:
        ok: Number of successful spans.
        fail: Number of failed or timed-out spans.
        partial: Number of partial spans.

    Returns:
        Rate from 0 to 1, or None when no span has finished.
    """
    done = ok + fail + partial
    return ok / done if done else None


def alert_card(level: str, title: str, impact: str, action: str, link: str | None = None) -> str:
    """Build a four-line alert message: incident, impact, action, link.

    Args:
        level: Level key in `LEVEL_LABEL`.
        title: The incident, one sentence.
        impact: Effect on operations.
        action: Command or button the operator should use.
        link: Link that opens the Control Room, if any.

    Returns:
        Multi-line text of at most 4 lines.
    """
    lines = [f"[{LEVEL_LABEL.get(level, level.upper())}] {title}", f"Ảnh hưởng: {impact}",
             f"Việc cần làm: {action}"]
    if link:
        lines.append(f"Xem: {link}")
    return "\n".join(lines)
