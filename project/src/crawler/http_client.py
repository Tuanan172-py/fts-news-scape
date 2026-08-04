"""
HTTP client với retry, rate limit per-domain, UA rotation.

1 class HTTPClient duy nhất cho tất cả scrapers.
Rate limit mặc định 3.0s/domain (spec §12), timeout ≤30s.
"""

from __future__ import annotations

import json
import random
import time
from urllib.parse import urlparse

try:
    # Dùng OS cert store (Windows) thay certifi — một số site VN (hnx.vn) serve
    # cert chain thiếu intermediate, certifi strict sẽ fail còn OS store thì không
    import truststore
    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover
    pass

import requests
from loguru import logger
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
]


class RateLimiter:
    """Rate limiter per domain — mỗi domain 1 bucket độc lập. Thread-safe."""

    def __init__(self, default_delay: float = 3.0):
        import threading
        self._last_request: dict[str, float] = {}
        self.default_delay = default_delay
        self._lock = threading.Lock()

    def wait(self, url: str, delay: float | None = None):
        domain = urlparse(url).netloc
        delay = delay if delay is not None else self.default_delay
        with self._lock:
            last = self._last_request.get(domain, 0)
            sleep_for = delay - (time.time() - last)
            # reserve slot trước khi sleep để thread khác thấy đúng thời điểm
            self._last_request[domain] = time.time() + max(0, sleep_for)
        if sleep_for > 0:
            time.sleep(sleep_for)


class HTTPClient:
    """HTTP client với retry (429/5xx), rate limit, UA rotation."""

    def __init__(self, rate_limit_delay: float = 3.0, max_retries: int = 3):
        self.rate_limiter = RateLimiter(rate_limit_delay)
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1.5,  # 1.5, 3, 6 seconds
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD", "POST"],  # POST = API query idempotent
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _get_headers(self, referer: str | None = None,
                     extra: dict | None = None) -> dict:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            # KHÔNG tự khai Accept-Encoding: requests chỉ advertise codec nó
            # decode được (br chỉ khi có brotli package) — tự khai "br" mà thiếu
            # decoder → bytes rác (vietnambiz/vietnamnet 2026-07-25)
            "DNT": "1",
            "Connection": "keep-alive",
        }
        if referer:
            headers["Referer"] = referer
        if extra:
            headers.update(extra)
        return headers

    def get(self, url: str, referer: str | None = None, timeout: int = 30,
            params: dict | None = None, headers: dict | None = None) -> str | None:
        """GET → text hoặc None. Retry + rate limit tự động."""
        self.rate_limiter.wait(url)
        try:
            resp = self.session.get(url, params=params, timeout=timeout,
                                    headers=self._get_headers(referer, headers))
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.RequestException as e:
            logger.warning("HTTP GET failed {}: {}", url, e)
            return None

    def get_bytes(self, url: str, referer: str | None = None, timeout: int = 30,
                  params: dict | None = None, headers: dict | None = None) -> bytes | None:
        """GET → raw bytes (caller tự decode — cần cho feed utf-16/BOM)."""
        self.rate_limiter.wait(url)
        try:
            resp = self.session.get(url, params=params, timeout=timeout,
                                    headers=self._get_headers(referer, headers))
            resp.raise_for_status()
            return resp.content
        except requests.exceptions.RequestException as e:
            logger.warning("HTTP GET failed {}: {}", url, e)
            return None

    def get_json(self, url: str, referer: str | None = None, timeout: int = 30,
                 params: dict | None = None, headers: dict | None = None):
        """GET trả JSON đã parse, hoặc None. Tự set Accept: application/json."""
        merged = {"Accept": "application/json, text/plain, */*"}
        if headers:
            merged.update(headers)
        text = self.get(url, referer=referer, timeout=timeout,
                        params=params, headers=merged)
        if text is None:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON from {}: {}", url, e)
            return None

    def post_json(self, url: str, data: dict | None = None,
                  json_body: dict | None = None, referer: str | None = None,
                  timeout: int = 30, headers: dict | None = None):
        """POST (form data hoặc JSON body) trả JSON đã parse, hoặc None."""
        self.rate_limiter.wait(url)
        merged = {"Accept": "application/json, text/plain, */*",
                  "X-Requested-With": "XMLHttpRequest"}
        if headers:
            merged.update(headers)
        try:
            resp = self.session.post(url, data=data, json=json_body, timeout=timeout,
                                     headers=self._get_headers(referer, merged))
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.warning("HTTP POST failed {}: {}", url, e)
            return None
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON from POST {}: {}", url, e)
            return None

    def get_response(self, url: str, referer: str | None = None, timeout: int = 30,
                     params: dict | None = None,
                     headers: dict | None = None) -> requests.Response | None:
        """GET trả nguyên Response (caller cần status/headers, vd FireAnt 401)."""
        self.rate_limiter.wait(url)
        try:
            return self.session.get(url, params=params, timeout=timeout,
                                    headers=self._get_headers(referer, headers))
        except requests.exceptions.RequestException as e:
            logger.warning("HTTP GET failed {}: {}", url, e)
            return None
