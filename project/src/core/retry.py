"""Retry and fallback handling for scrape cycles."""

from __future__ import annotations

from loguru import logger
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential)

from src.core.base_scraper import BaseScraper
from src.core.models import ScrapeResult


class TransientError(Exception):
    """Raised for a temporary failure that permits a retry."""


class PermanentError(Exception):
    """Raised for a permanent failure that retrying cannot fix."""


def _cycle_failed(result: ScrapeResult) -> bool:
    """Check whether a scrape cycle failed completely.

    Args:
        result: Scrape result of the scraper.

    Returns:
        True if no article was fetched and errors occurred.
    """
    return result.fetched == 0 and bool(result.errors)


@retry(stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=2, min=2, max=30),
       retry=retry_if_exception_type(TransientError),
       reraise=True)
def _attempt(scraper: BaseScraper) -> ScrapeResult:
    result = scraper.run()
    if _cycle_failed(result) and not scraper.disabled:
        # A disabled scraper is a permanent error and is not retried.
        raise TransientError(f"{scraper.name}: {result.errors[:2]}")
    return result


def run_with_retry(scraper: BaseScraper) -> ScrapeResult:
    """Run a scraper with exponential-backoff retry, at most 3 attempts.

    Args:
        scraper: Scraper to run.

    Returns:
        ScrapeResult with the outcome or the accumulated errors.
    """
    try:
        return _attempt(scraper)
    except TransientError as e:
        logger.error("[{}] all retries exhausted: {}", scraper.name, e)
        return ScrapeResult(scraper=scraper.name,
                            errors=[f"retries exhausted: {e}"])


def run_with_fallback(primary: BaseScraper,
                      fallback: BaseScraper | None = None) -> ScrapeResult:
    """Run the primary scraper and switch to the fallback scraper if it fails.

    Args:
        primary: Scraper that runs first.
        fallback: Optional scraper used when the primary one fails.

    Returns:
        Final ScrapeResult from the primary or the fallback scraper.
    """
    result = run_with_retry(primary)
    if not _cycle_failed(result) or fallback is None:
        return result
    logger.warning("[{}] primary method failed — switching to fallback [{}]",
                   primary.name, fallback.name)
    fb_result = run_with_retry(fallback)
    fb_result.errors = result.errors + fb_result.errors
    return fb_result
