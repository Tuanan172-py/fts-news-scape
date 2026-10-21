"""Enforce the robots.txt rules of source domains."""

from __future__ import annotations

import threading
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from loguru import logger


class RobotsGate:
    """Gate crawl permission based on robots.txt (thread-safe).

    Attributes:
        http: HTTP client used to download robots.txt.
        ttl: Lifetime of the robots cache in seconds.
    """

    def __init__(self, http, ttl: float = 86400.0):
        """Create the gate with an empty robots cache.

        Args:
            http: HTTP client used to download robots.txt.
            ttl: Lifetime of the robots cache in seconds.
        """
        self.http = http
        self.ttl = ttl
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
            rp = None
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
        """Check whether robots.txt allows crawling a URL.

        Args:
            url: URL to check.
            ua: User-Agent name to check.

        Returns:
            True if allowed, or if robots.txt could not be loaded (fail-open).
        """
        rp = self._get_parser(urlparse(url).netloc)
        if rp is None:
            return True
        try:
            return rp.can_fetch(ua, url)
        except Exception:  # pragma: no cover - defensive
            return True

    def crawl_delay(self, domain: str, ua: str = "*") -> float | None:
        """Get the crawl-delay value from robots.txt, if any.

        Args:
            domain: Domain to check.
            ua: User-Agent name to check.

        Returns:
            Crawl delay in seconds, or None if not specified.
        """
        rp = self._get_parser(domain)
        if rp is None:
            return None
        try:
            d = rp.crawl_delay(ua)
            return float(d) if d is not None else None
        except Exception:  # pragma: no cover - defensive
            return None
