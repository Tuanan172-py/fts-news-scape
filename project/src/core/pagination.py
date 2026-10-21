"""Paginate by watermark, reading on until a page contains only articles already in the store."""

from __future__ import annotations

from typing import Callable

DEFAULT_MAX_PAGES = 8


def paginate_until_known(
    fetch_page: Callable[[int], list[dict] | None],
    key_of: Callable[[dict], str],
    known: Callable[[list[str]], set[str]],
    *,
    min_pages: int = 1,
    max_pages: int = DEFAULT_MAX_PAGES,
    errors: list[str] | None = None,
    label: str = "",
) -> list[dict]:
    """Read listing pages until every item on a page is already captured.

    Args:
        fetch_page: Callable taking a 1-based page number; returns the page items, an empty list past the last page, or None on error.
        key_of: Callable returning the article key of an item, used to look up the discovery ledger.
        known: Callable taking a list of keys and returning the subset already captured.
        min_pages: Minimum number of pages always read, even if the first page holds only known articles.
        max_pages: Safety cap on pages per run.
        errors: Scraper error list; a page failure or hitting the cap appends a message.
        label: Source or section label included in error messages.

    Returns:
        Items read, in page order.
    """
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        items = fetch_page(page)
        if items is None:
            if errors is not None:
                errors.append(f"{label}: tải trang {page} lỗi, dừng phân trang")
            return out
        if not items:
            return out
        out.extend(items)
        if page >= min_pages:
            keys = [k for k in (key_of(i) for i in items) if k]
            if keys and set(keys) <= known(keys):
                return out
    if errors is not None:
        errors.append(f"{label}: chạm trần {max_pages} trang mà chưa gặp bài đã biết")
    return out
