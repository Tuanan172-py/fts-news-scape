"""Apply per-source exponential backoff when a site signals throttling."""

from __future__ import annotations

import threading
import time

from loguru import logger

_BACKOFF_STEPS = (2.0, 4.0, 8.0, 16.0)


class SourceBackoff:
    """Track request spacing independently per domain (thread-safe)."""

    def __init__(self):
        """Create an empty backoff state."""
        self._state: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _delay_for(self, consecutive: int) -> float:
        idx = min(consecutive, len(_BACKOFF_STEPS) - 1)
        return _BACKOFF_STEPS[idx]

    def before_fetch(self, domain: str) -> None:
        """Pause the thread if the domain is in its cool-down period.

        Args:
            domain: Domain about to receive a request.
        """
        with self._lock:
            st = self._state.get(domain)
            wait_until = st["next_allowed_ts"] if st else 0.0
        remaining = wait_until - time.time()
        if remaining > 0:
            logger.info("[{}] backoff pause {:.1f}s", domain, remaining)
            time.sleep(remaining)

    def observe(self, domain: str, status: int | None) -> None:
        """Record an HTTP response status to update the cool-down time.

        Args:
            domain: Domain that answered.
            status: HTTP status code received.
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
