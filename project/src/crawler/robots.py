"""Kiểm soát tuân thủ tệp robots.txt của các tên miền nguồn tin."""

from __future__ import annotations

import threading
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from loguru import logger


class RobotsGate:
    """Cổng kiểm tra quyền thu thập dữ liệu dựa trên tệp robots.txt (Thread-safe).

    Attributes:
        http: Client HTTP dùng để tải tệp robots.txt.
        ttl: Thời gian sống của bộ nhớ đệm robots tính bằng giây.
    """

    def __init__(self, http, ttl: float = 86400.0):
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
        """Kiểm tra đường dẫn URL có được phép thu thập theo robots.txt hay không.

        Args:
            url: Địa chỉ URL cần kiểm tra quyền truy cập.
            ua: Tên User-Agent cần kiểm tra.

        Returns:
            True nếu được phép hoặc khi gặp lỗi tải robots.txt (fail-open).
        """
        rp = self._get_parser(urlparse(url).netloc)
        if rp is None:
            return True
        try:
            return rp.can_fetch(ua, url)
        except Exception:  # pragma: no cover - defensive
            return True

    def crawl_delay(self, domain: str, ua: str = "*") -> float | None:
        """Lấy giá trị khoảng cách thu thập (crawl-delay) từ robots.txt nếu có.

        Args:
            domain: Tên miền cần kiểm tra.
            ua: Tên User-Agent cần kiểm tra.

        Returns:
            Khoảng cách thu thập tính bằng giây hoặc None nếu không quy định.
        """
        rp = self._get_parser(domain)
        if rp is None:
            return None
        try:
            d = rp.crawl_delay(ua)
            return float(d) if d is not None else None
        except Exception:  # pragma: no cover - defensive
            return None
