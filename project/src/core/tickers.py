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


# Place-name context BEFORE a code: "TP.HCM", "TP HCM", "Thành phố HCM", "UBND HCM", "khu vực HCM".
LOCATION_LEFT_GUARD_RE = re.compile(
    r"(?:\bT\.?\s*P\.?\s*|\bthành\s+phố\s+|\bUBND\s*|\bkhu\s+vực\s*)$", re.IGNORECASE)
# Place-name context AFTER a code: "HCM City", "HCMC".
LOCATION_RIGHT_GUARD_RE = re.compile(r"^(?:\s*City\b|C\b)")


def is_location_context(text: str, start: int, end: int) -> bool:
    """Check whether a three-letter code at a position is part of a place name.

    Args:
        text: Source text containing the code.
        start: Start offset of the code in the text.
        end: End offset of the code in the text.

    Returns:
        True when the code belongs to a place name such as "TP.HCM", otherwise False.
    """
    return bool(LOCATION_LEFT_GUARD_RE.search(text[:start])
                or LOCATION_RIGHT_GUARD_RE.match(text[end:]))


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
    for m in _TICKER_RE.finditer(text):
        code = m.group()
        if code not in allowed or code in seen:
            continue
        if is_location_context(text, m.start(), m.end()):
            continue
        seen.append(code)
    return seen
