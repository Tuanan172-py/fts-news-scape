"""Định dạng và nhãn tiếng Việt dùng chung cho tin Telegram và Phòng điều khiển."""

from __future__ import annotations

import math
import re

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _round(x: float) -> int:
    """Làm tròn nửa lên, đúng quy ước của `Math.round` trong trình duyệt."""
    return int(math.floor(x + 0.5))


# Mức cảnh báo: nhãn chữ, không dùng biểu tượng.
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
           "manual": "Người chạy", "retry": "Chạy lại"}

# Bảng gửi cho trang web qua `/api/labels`; mọi nhãn chữ của giao diện lấy từ đây.
LABELS = {
    "level": LEVEL_LABEL, "wave_status": WAVE_STATUS, "span_status": SPAN_STATUS,
    "span_kind": SPAN_KIND, "node_state": NODE_STATE, "breaker_state": BREAKER_STATE,
    "failure_class": FAILURE_CLASS, "capture_mode": CAPTURE_MODE,
    "proposal_status": PROPOSAL_STATUS, "agent_status": AGENT_STATUS, "trigger": TRIGGER,
}


def label(table: dict[str, str], key: str | None) -> str:
    """Tra nhãn tiếng Việt, trả lại khoá gốc khi chưa có nhãn.

    Args:
        table: Bảng nhãn.
        key: Giá trị cần tra.

    Returns:
        Nhãn tiếng Việt, hoặc khoá gốc, hoặc dấu gạch ngang khi không có giá trị.
    """
    if key is None or key == "":
        return "–"
    return table.get(str(key), str(key))


def fmt_int(value: float | int | None) -> str:
    """Định dạng số nguyên theo vi-VN, dấu chấm ngăn nhóm nghìn.

    Args:
        value: Số cần định dạng.

    Returns:
        Chuỗi như `1.234`, hoặc dấu gạch ngang khi thiếu giá trị.
    """
    if value is None:
        return "–"
    return f"{_round(value):,}".replace(",", ".")


def fmt_pct(ratio: float | None) -> str:
    """Định dạng tỷ lệ thành phần trăm nguyên.

    Args:
        ratio: Tỷ lệ trong khoảng 0 đến 1.

    Returns:
        Chuỗi như `56%`, hoặc dấu gạch ngang khi thiếu giá trị.
    """
    if ratio is None:
        return "–"
    return f"{_round(ratio * 100)}%"


def fmt_duration(seconds: float | None) -> str:
    """Định dạng thời lượng: ms dưới 1 s, một số lẻ dưới 10 s, nguyên từ 10 s, "ph" từ 60 s.

    Args:
        seconds: Số giây.

    Returns:
        Chuỗi như `66 ms`, `5,4 s`, `54 s`, `1 ph 54 s`.
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
    """Cho biết chuỗi bắt đầu bằng ngày dạng `yyyy-MM-dd`."""
    return bool(_ISO_DATE.match(text))


def fmt_datetime(iso: str | None) -> str:
    """Định dạng thời điểm ISO thành `dd/MM HH:mm`, hoặc `dd/MM` khi chỉ có ngày.

    Cắt chuỗi theo vị trí, không đổi múi giờ, để khớp từng ký tự với trang web.

    Args:
        iso: Chuỗi ISO 8601.

    Returns:
        Chuỗi như `01/10 14:34`; dấu gạch ngang khi trống; chuỗi gốc khi không phải ISO.
    """
    if not iso:
        return "–"
    s = str(iso)
    if not _is_iso(s):
        return s
    day = f"{s[8:10]}/{s[5:7]}"
    return day if len(s) < 16 else f"{day} {s[11:16]}"


def fmt_time(iso: str | None) -> str:
    """Định dạng thời điểm ISO thành `HH:mm`.

    Args:
        iso: Chuỗi ISO 8601.

    Returns:
        Chuỗi như `14:34`; dấu gạch ngang khi trống hoặc chỉ có ngày; chuỗi gốc khi không phải ISO.
    """
    if not iso:
        return "–"
    s = str(iso)
    if not _is_iso(s):
        return s
    return s[11:16] if len(s) >= 16 else "–"


def fmt_date(iso: str | None) -> str:
    """Định dạng ngày ISO thành `dd/MM/yyyy`.

    Args:
        iso: Chuỗi ngày hoặc thời điểm ISO 8601.

    Returns:
        Chuỗi như `30/10/2026`; dấu gạch ngang khi trống; chuỗi gốc khi không phải ISO.
    """
    if not iso:
        return "–"
    s = str(iso)
    if not _is_iso(s):
        return s
    return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"


def clip_lines(text: str, max_chars: int = 3800) -> str:
    """Cắt văn bản ở ranh giới dòng, không cắt giữa dòng.

    Args:
        text: Văn bản nhiều dòng.
        max_chars: Số ký tự tối đa (Telegram cho 4096).

    Returns:
        Văn bản gốc nếu đủ ngắn, ngược lại các dòng đầu kèm dòng báo số dòng bị bỏ.
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
    """Tính tỷ lệ thành công của các span đã kết thúc.

    Span đang chạy và span bỏ qua không tính. Span một phần tính vào mẫu số nhưng không
    tính là thành công.

    Args:
        ok: Số span thành công.
        fail: Số span lỗi hoặc quá hạn.
        partial: Số span một phần.

    Returns:
        Tỷ lệ 0 đến 1, hoặc None khi chưa có span nào kết thúc.
    """
    done = ok + fail + partial
    return ok / done if done else None


def alert_card(level: str, title: str, impact: str, action: str, link: str | None = None) -> str:
    """Dựng tin cảnh báo bốn dòng: sự việc, ảnh hưởng, hành động, đường dẫn.

    Args:
        level: Mức trong `LEVEL_LABEL`.
        title: Sự việc, một câu.
        impact: Ảnh hưởng tới vận hành.
        action: Lệnh hoặc nút người vận hành cần dùng.
        link: Đường dẫn mở Phòng điều khiển, nếu có.

    Returns:
        Văn bản nhiều dòng, tối đa 4 dòng.
    """
    lines = [f"[{LEVEL_LABEL.get(level, level.upper())}] {title}", f"Ảnh hưởng: {impact}",
             f"Việc cần làm: {action}"]
    if link:
        lines.append(f"Xem: {link}")
    return "\n".join(lines)
