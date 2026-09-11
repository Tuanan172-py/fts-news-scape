"""Tiện ích cấu hình luồng xuất nhập chuẩn UTF-8 trên môi trường hệ điều hành Windows."""

from __future__ import annotations

import sys


def force_utf8_stdio() -> None:
    """Thiết lập mã hóa UTF-8 cho stdout và stderr nhằm phòng chống lỗi ký tự trên Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
