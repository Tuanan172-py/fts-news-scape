"""
SourceBackoff — cool-down cấp-source khi bị throttle (D4).

Khác với urllib3 Retry (retry trong 1 request): đây là pause GIỮA các lần enrich
cho cùng 1 domain. Nhận 429/503 → exponential backoff 2→4→8→16s (cap 16s);
gặp 2xx → reset. Thread-safe (APScheduler worker). Không raise.
"""

from __future__ import annotations

import threading
import time

from loguru import logger

_BACKOFF_STEPS = (2.0, 4.0, 8.0, 16.0)


class SourceBackoff:
    def __init__(self):
        # domain -> {"consecutive": int, "next_allowed_ts": float}
        self._state: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _delay_for(self, consecutive: int) -> float:
        idx = min(consecutive, len(_BACKOFF_STEPS) - 1)
        return _BACKOFF_STEPS[idx]

    def before_fetch(self, domain: str) -> None:
        """Chờ hết cool-down còn lại (nếu có) trước khi fetch."""
        with self._lock:
            st = self._state.get(domain)
            wait_until = st["next_allowed_ts"] if st else 0.0
        remaining = wait_until - time.time()
        if remaining > 0:
            logger.info("[{}] backoff pause {:.1f}s", domain, remaining)
            time.sleep(remaining)

    def observe(self, domain: str, status: int | None) -> None:
        """Cập nhật state theo status phản hồi."""
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
