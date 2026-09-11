"""Tiện ích khóa cố vấn (advisory lock) cho tiến trình lập lịch scheduler."""

from __future__ import annotations

import os
import socket

SCHEDULER_LOCK_STALE_SECONDS = 2400  # 40 phút


def lock_owner() -> str:
    """Tạo định danh duy nhất cho tiến trình sở hữu khóa dạng hostname:pid.

    Returns:
        Chuỗi định danh tiến trình hiện tại.
    """
    return f"{socket.gethostname()}:{os.getpid()}"
