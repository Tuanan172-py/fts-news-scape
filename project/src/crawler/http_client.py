"""HTTP client with rate limiting, retry and User-Agent rotation."""

from __future__ import annotations

import json
import random
import time
from urllib.parse import urlparse

try:
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
    """Throttle the request rate independently per domain (thread-safe).

    Attributes:
        default_delay: Default spacing between two requests in seconds.
    """

    def __init__(self, default_delay: float = 3.0):
        """Create a limiter with no request history.

        Args:
            default_delay: Default spacing between two requests in seconds.
        """
        import threading
        self._last_request: dict[str, float] = {}
        self.default_delay = default_delay
        self._lock = threading.Lock()

    def wait(self, url: str, delay: float | None = None):
        """Block the thread to keep a safe gap between requests to the same domain.

        Args:
            url: Target URL, used to identify the domain.
            delay: Optional spacing in seconds; defaults to `default_delay`.
        """
        domain = urlparse(url).netloc
        delay = delay if delay is not None else self.default_delay
        with self._lock:
            last = self._last_request.get(domain, 0)
            sleep_for = delay - (time.time() - last)
            self._last_request[domain] = time.time() + max(0, sleep_for)
        if sleep_for > 0:
            time.sleep(sleep_for)


class HTTPClient:
    """Manage an HTTP session with automatic network-error handling, rate limiting and proxies.

    Attributes:
        rate_limiter: Limiter that throttles the request rate.
        session: requests.Session with the retry adapter mounted.
    """

    def __init__(self, rate_limit_delay: float = 3.0, max_retries: int = 3):
        """Create the session with a retry adapter and a rate limiter.

        Args:
            rate_limit_delay: Default spacing between requests to one domain, in seconds.
            max_retries: Maximum retries for transient HTTP errors.
        """
        self.rate_limiter = RateLimiter(rate_limit_delay)
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self._proxy_pool: list[str] = []
        self._proxy_idx: int = 0

    def set_proxy_pool(self, proxies: list[str] | None) -> None:
        """Configure the proxy list used for rotation.

        Args:
            proxies: Proxy addresses, or None to disable.
        """
        self._proxy_pool = list(proxies or [])
        self._proxy_idx = 0

    def rotate_proxy(self) -> None:
        """Switch the session to the next proxy in the list."""
        if not self._proxy_pool:
            return
        self._proxy_idx = (self._proxy_idx + 1) % len(self._proxy_pool)
        proxy = self._proxy_pool[self._proxy_idx]
        self.session.proxies = {"http": proxy, "https": proxy}
        logger.info("rotated proxy → {}", proxy)

    def _get_headers(self, referer: str | None = None,
                     extra: dict | None = None) -> dict:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
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
        """Send an HTTP GET request and return the text body.

        Args:
            url: Target URL.
            referer: Optional Referer header.
            timeout: Maximum wait in seconds.
            params: URL query parameters as a dict.
            headers: Additional HTTP headers.

        Returns:
            Response text, or None if the request failed.
        """
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
        """Send an HTTP GET request and return the raw bytes body.

        Args:
            url: Target URL.
            referer: Optional Referer header.
            timeout: Maximum wait in seconds.
            params: URL query parameters as a dict.
            headers: Additional HTTP headers.

        Returns:
            Binary content received, or None if the request failed.
        """
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
        """Send an HTTP GET request and decode the JSON result.

        Args:
            url: Target URL.
            referer: Optional Referer header.
            timeout: Maximum wait in seconds.
            params: URL query parameters as a dict.
            headers: Additional HTTP headers.

        Returns:
            Decoded JSON data, or None on failure or malformed JSON.
        """
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
        """Send an HTTP POST request and decode the JSON response.

        Args:
            url: Target URL.
            data: Data sent as URL-encoded form.
            json_body: Data sent as the JSON body.
            referer: Optional Referer header.
            timeout: Maximum wait in seconds.
            headers: Additional HTTP headers.

        Returns:
            Decoded JSON data, or None on failure or malformed JSON.
        """
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
        """Send an HTTP GET request and return the original requests.Response.

        Args:
            url: Target URL.
            referer: Optional Referer header.
            timeout: Maximum wait in seconds.
            params: URL query parameters as a dict.
            headers: Additional HTTP headers.

        Returns:
            The requests.Response, or None on a connection failure.
        """
        self.rate_limiter.wait(url)
        try:
            return self.session.get(url, params=params, timeout=timeout,
                                    headers=self._get_headers(referer, headers))
        except requests.exceptions.RequestException as e:
            logger.warning("HTTP GET failed {}: {}", url, e)
            return None
