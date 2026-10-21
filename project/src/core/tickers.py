"""Detect and tag stock tickers that appear in text against a watchlist."""

from __future__ import annotations

import re

_TICKER_RE = re.compile(r"\b[A-Z]{3}\b")

# Common three-letter uppercase words excluded to reduce false positives.
DEFAULT_STOPLIST = frozenset({
    "GDP", "CPI", "PMI", "FED", "USD", "EUR", "JPY", "CNY", "VND",
    "CEO", "CFO", "COO", "HHĐ", "ETF", "IPO", "ROE", "ROA", "EPS",
    "HNX", "OTC", "GMT", "UBC", "TOD",
})


def tag_tickers(text: str, watchlist: list[str] | set[str],
                stoplist: frozenset[str] = DEFAULT_STOPLIST) -> list[str]:
    """Extract the unique stock tickers that appear in a text.

    Args:
        text: Text to search for tickers.
        watchlist: Tickers being watched.
        stoplist: Three-letter uppercase words to exclude.

    Returns:
        Matching tickers in order of first appearance.
    """
    if not text:
        return []
    allowed = {t.upper() for t in watchlist} - stoplist
    seen: list[str] = []
    for m in _TICKER_RE.findall(text):
        if m in allowed and m not in seen:
            seen.append(m)
    return seen
