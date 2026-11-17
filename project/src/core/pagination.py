"""Paginate by watermark, reading on until a page brings nothing new to the store."""

from __future__ import annotations

from typing import Callable

DEFAULT_MAX_PAGES = 8
CAP_MARK = "chạm trần"   # error text the heartbeat counts as a pagination cap hit


def paginate_until_known(
    fetch_page: Callable[[int], list[dict] | None],
    key_of: Callable[[dict], str],
    known: Callable[[list[str]], set[str]],
    *,
    min_pages: int = 1,
    max_pages: int = DEFAULT_MAX_PAGES,
    errors: list[str] | None = None,
    label: str = "",
    reached: Callable[[list[dict]], bool] | None = None,
) -> list[dict]:
    """Read listing pages until a page holds no article that is both new to this run and uncaptured.

    Only items not seen on an earlier page of the same run count. A featured article repeated
    on every page would otherwise keep each page "unknown" until it is captured, which happens
    after pagination, so the run would always hit the cap.

    Args:
        fetch_page: Callable taking a 1-based page number; returns the page items, an empty list past the last page, or None on error.
        key_of: Callable returning the article key of an item, used to look up the discovery ledger.
        known: Callable taking a list of keys and returning the subset already captured.
        min_pages: Minimum number of pages always read, even if the first page holds only known articles.
        max_pages: Safety cap on pages per run.
        errors: Scraper error list; a page failure or hitting the cap appends a message.
        label: Source or section label included in error messages.
        reached: Optional callable telling whether a page reaches back past the catch-up
            cutoff. When given, it replaces the watermark rule: the run stops at the first
            page that reaches the cutoff, known or not, because everything older was read by
            the last complete run; a fully known page newer than the cutoff does not stop it.

    Returns:
        Items read, in page order.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        items = fetch_page(page)
        if items is None:
            if errors is not None:
                errors.append(f"{label}: tải trang {page} lỗi, dừng phân trang")
            return out
        if not items:
            return out
        keys = [key_of(i) for i in items]
        out.extend(i for i, k in zip(items, keys) if not k or k not in seen)
        fresh = [k for k in dict.fromkeys(keys) if k and k not in seen]
        seen.update(fresh)
        if page < min_pages:
            continue
        if reached is not None:
            if reached(items):
                return out
        elif not fresh or set(fresh) <= known(fresh):
            return out
    if errors is not None:
        errors.append(f"{label}: {CAP_MARK} {max_pages} trang mà chưa gặp bài đã biết")
    return out
