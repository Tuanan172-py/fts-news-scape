"""
Tiện ích advisory lock cho scheduler (Fix F — chống chạy 2 scheduler cùng lúc).

Lock lưu trong DB (`pipeline_state` qua ArticleStore.try_acquire_lock/refresh_lock).
Nhịp tim (refresh) chạy mỗi capture cycle (~15'); STALE phải LỚN HƠN interval để lock
không bị cướp giữa 2 cycle. 40' đủ tolerate misfire; chủ cũ chết → sau 40' tiến trình
mới được phép chiếm lại lock.
"""

from __future__ import annotations

import os
import socket

SCHEDULER_LOCK_STALE_SECONDS = 2400  # 40 phút


def lock_owner() -> str:
    """Định danh tiến trình giữ lock: host:pid."""
    return f"{socket.gethostname()}:{os.getpid()}"
