"""
Retry & fallback — spec §4.3: primary fail → fallback tự động, retry 3 lần.

Transport-level retry (429/5xx) đã có trong HTTPClient (urllib3 Retry).
Lớp này retry ở mức operation (cả lượt scraper.run) + fallback method chain.
"""

from __future__ import annotations

from loguru import logger
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential)

from src.core.base_scraper import BaseScraper
from src.core.models import ScrapeResult


class TransientError(Exception):
    """Lỗi tạm thời (timeout, network, 429/5xx) — đáng retry."""


class PermanentError(Exception):
    """Lỗi vĩnh viễn (401/403/404, schema break) — không retry."""


def _cycle_failed(result: ScrapeResult) -> bool:
    """Cycle coi là fail khi không fetch được gì VÀ có lỗi (chết hẳn nguồn)."""
    return result.fetched == 0 and bool(result.errors)


@retry(stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=2, min=2, max=30),
       retry=retry_if_exception_type(TransientError),
       reraise=True)
def _attempt(scraper: BaseScraper) -> ScrapeResult:
    result = scraper.run()
    if _cycle_failed(result) and not scraper.disabled:
        # disabled (vd FireAnt 401) là permanent — không retry
        raise TransientError(f"{scraper.name}: {result.errors[:2]}")
    return result


def run_with_retry(scraper: BaseScraper) -> ScrapeResult:
    """Chạy scraper với 3 attempts (backoff 2-30s). Không bao giờ raise."""
    try:
        return _attempt(scraper)
    except TransientError as e:
        logger.error("[{}] all retries exhausted: {}", scraper.name, e)
        return ScrapeResult(scraper=scraper.name,
                            errors=[f"retries exhausted: {e}"])


def run_with_fallback(primary: BaseScraper,
                      fallback: BaseScraper | None = None) -> ScrapeResult:
    """Primary (3 retries) → nếu vẫn fail và có fallback → fallback (3 retries).

    Graceful degradation: luôn trả ScrapeResult, không raise.
    """
    result = run_with_retry(primary)
    if not _cycle_failed(result) or fallback is None:
        return result
    logger.warning("[{}] primary method failed — switching to fallback [{}]",
                   primary.name, fallback.name)
    fb_result = run_with_retry(fallback)
    fb_result.errors = result.errors + fb_result.errors
    return fb_result
