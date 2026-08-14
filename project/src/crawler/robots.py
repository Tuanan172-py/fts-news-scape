"""
RobotsGate — kiểm tra robots.txt trước khi fetch trang chi tiết (AC9).

Stdlib `urllib.robotparser`, zero-dependency. Cache per-domain (TTL 24h).
FAIL-OPEN: robots.txt lỗi/không tải được → cho phép + WARN (không chặn pipeline
vì robots outage). Fetch robots qua HTTPClient để đi chung rate limit/UA.
"""

from __future__ import annotations

import threading
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from loguru import logger


class RobotsGate:
    def __init__(self, http, ttl: float = 86400.0):
        self.http = http
        self.ttl = ttl
        # domain -> (RobotFileParser|None, fetched_ts)  (None = fail-open cached)
        self._cache: dict[str, tuple[RobotFileParser | None, float]] = {}
        self._lock = threading.Lock()

    def _get_parser(self, domain: str) -> RobotFileParser | None:
        now = time.time()
        with self._lock:
            entry = self._cache.get(domain)
            if entry and now - entry[1] < self.ttl:
                return entry[0]

        rp: RobotFileParser | None = RobotFileParser()
        text = None
        try:
            text = self.http.get(f"https://{domain}/robots.txt", timeout=15)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("robots fetch error {}: {}", domain, e)

        if text is None:
            rp = None  # fail-open
        else:
            try:
                rp.parse(text.splitlines())
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("robots parse error {}: {}", domain, e)
                rp = None

        with self._lock:
            self._cache[domain] = (rp, now)
        return rp

    def allowed(self, url: str, ua: str = "*") -> bool:
        rp = self._get_parser(urlparse(url).netloc)
        if rp is None:
            return True  # fail-open
        try:
            return rp.can_fetch(ua, url)
        except Exception:  # pragma: no cover - defensive
            return True

    def crawl_delay(self, domain: str, ua: str = "*") -> float | None:
        rp = self._get_parser(domain)
        if rp is None:
            return None
        try:
            d = rp.crawl_delay(ua)
            return float(d) if d is not None else None
        except Exception:  # pragma: no cover - defensive
            return None
