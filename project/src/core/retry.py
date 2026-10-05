"""Cơ chế thử lại và chuyển đổi dự phòng (retry & fallback) cho chu trình thu thập."""

from __future__ import annotations

from loguru import logger
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential)

from src.core.base_scraper import BaseScraper
from src.core.models import ScrapeResult


class TransientError(Exception):
    """Lỗi tạm thời cho phép kích hoạt cơ chế thử lại."""


class PermanentError(Exception):
    """Lỗi vĩnh viễn không thể khắc phục qua thử lại."""


def _cycle_failed(result: ScrapeResult) -> bool:
    """Kiểm tra chu kỳ thu thập có thất bại hoàn toàn hay không.

    Args:
        result: Kết quả thu thập của scraper.

    Returns:
        True nếu không thu thập được bài viết nào và có lỗi phát sinh.
    """
    return result.fetched == 0 and bool(result.errors)


@retry(stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=2, min=2, max=30),
       retry=retry_if_exception_type(TransientError),
       reraise=True)
def _attempt(scraper: BaseScraper) -> ScrapeResult:
    result = scraper.run()
    if _cycle_failed(result) and not scraper.disabled:
        # Scraper bị disable là permanent error, không thử lại.
        raise TransientError(f"{scraper.name}: {result.errors[:2]}")
    return result


def run_with_retry(scraper: BaseScraper) -> ScrapeResult:
    """Thực thi scraper với cơ chế thử lại lũy thừa tối đa 3 lần.

    Args:
        scraper: Đối tượng BaseScraper cần thực thi.

    Returns:
        Đối tượng ScrapeResult chứa kết quả hoặc danh sách lỗi tích lũy.
    """
    try:
        return _attempt(scraper)
    except TransientError as e:
        logger.error("[{}] all retries exhausted: {}", scraper.name, e)
        return ScrapeResult(scraper=scraper.name,
                            errors=[f"retries exhausted: {e}"])


def run_with_fallback(primary: BaseScraper,
                      fallback: BaseScraper | None = None) -> ScrapeResult:
    """Thực thi scraper chính và tự động chuyển sang scraper dự phòng nếu thất bại.

    Args:
        primary: Scraper chính được ưu tiên chạy trước.
        fallback: Scraper dự phòng khi scraper chính gặp sự cố (tùy chọn).

    Returns:
        Đối tượng ScrapeResult cuối cùng từ scraper chính hoặc dự phòng.
    """
    result = run_with_retry(primary)
    if not _cycle_failed(result) or fallback is None:
        return result
    logger.warning("[{}] primary method failed — switching to fallback [{}]",
                   primary.name, fallback.name)
    fb_result = run_with_retry(fallback)
    fb_result.errors = result.errors + fb_result.errors
    return fb_result
