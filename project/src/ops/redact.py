"""Che bí mật trong văn bản trước khi ghi vào sự kiện, cảnh báo, nhật ký hoặc prompt."""

from __future__ import annotations

import re
from typing import Any

MASK = "***"

_PATTERNS = (
    # Token bot Telegram, kể cả khi nằm trong URL `.../bot<token>/sendMessage`.
    re.compile(r"(?<!\d)\d{6,12}:[A-Za-z0-9_-]{30,}"),
    # URL ping healthchecks.io: phần định danh sau tên miền là bí mật.
    re.compile(r"(?<=hc-ping\.com/)[A-Za-z0-9_-]{8,}(?:/[A-Za-z0-9_-]+)?"),
    # Khoá API dạng `sk-...` (OpenRouter, OpenAI) và tiêu đề Bearer.
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)(?<=bearer )[A-Za-z0-9._~+/=-]{16,}"),
)


def redact(text: str | None) -> str | None:
    """Thay mọi chuỗi trông như bí mật bằng dấu che.

    Args:
        text: Văn bản cần che, có thể None.

    Returns:
        Văn bản đã che, hoặc None khi đầu vào là None.
    """
    if not text:
        return text
    out = str(text)
    for pat in _PATTERNS:
        out = pat.sub(MASK, out)
    return out


def redact_data(value: Any) -> Any:
    """Che bí mật trong mọi chuỗi của một cấu trúc từ điển hoặc danh sách lồng nhau.

    Args:
        value: Giá trị bất kỳ.

    Returns:
        Bản sao đã che; giá trị không phải chuỗi giữ nguyên.
    """
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_data(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_data(v) for v in value]
    return value
