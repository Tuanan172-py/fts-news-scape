"""Cơ chế giãn cách lũy thừa (exponential backoff) cấp độ nguồn tin khi gặp hiện tượng nghẽn mạng."""

from __future__ import annotations

import threading
import time

from loguru import logger

_BACKOFF_STEPS = (2.0, 4.0, 8.0, 16.0)


class SourceBackoff:
    """Quản lý thời gian giãn cách yêu cầu độc lập theo từng tên miền (Thread-safe)."""

    def __init__(self):
        self._state: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _delay_for(self, consecutive: int) -> float:
        idx = min(consecutive, len(_BACKOFF_STEPS) - 1)
        return _BACKOFF_STEPS[idx]

    def before_fetch(self, domain: str) -> None:
        """Tạm dừng luồng nếu tên miền đang trong khoảng thời gian hạ nhiệt.

        Args:
            domain: Tên miền chuẩn bị gửi yêu cầu.
        """
        with self._lock:
            st = self._state.get(domain)
            wait_until = st["next_allowed_ts"] if st else 0.0
        remaining = wait_until - time.time()
        if remaining > 0:
            logger.info("[{}] backoff pause {:.1f}s", domain, remaining)
            time.sleep(remaining)

    def observe(self, domain: str, status: int | None) -> None:
        """Ghi nhận mã trạng thái phản hồi HTTP để cập nhật thời gian hạ nhiệt.

        Args:
            domain: Tên miền nhận phản hồi.
            status: Mã trạng thái HTTP nhận được.
        """
        with self._lock:
            st = self._state.setdefault(
                domain, {"consecutive": 0, "next_allowed_ts": 0.0})
            if status in (429, 503):
                delay = self._delay_for(st["consecutive"])
                st["consecutive"] = min(st["consecutive"] + 1, len(_BACKOFF_STEPS))
                st["next_allowed_ts"] = time.time() + delay
            elif status is not None and 200 <= status < 300:
                st["consecutive"] = 0
                st["next_allowed_ts"] = 0.0
