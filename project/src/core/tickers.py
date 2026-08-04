"""
Ticker tagging — match mã cổ phiếu (3 ký tự in hoa) trong text với watchlist.

Dùng cho nguồn không có symbol filter server-side (TNCK, Vietstock RSS...).
"""

from __future__ import annotations

import re

_TICKER_RE = re.compile(r"\b[A-Z]{3}\b")

# Từ 3 chữ in hoa hay gặp trong tin tài chính nhưng KHÔNG phải mã cổ phiếu.
# VND nằm đây vì thường là đơn vị tiền tệ ("nghìn tỷ VND") — false positive
# nhiều hơn true positive; tin VNDirect vẫn được cover qua nguồn symbol-based.
DEFAULT_STOPLIST = frozenset({
    "GDP", "CPI", "PMI", "FED", "USD", "EUR", "JPY", "CNY", "VND",
    "CEO", "CFO", "COO", "HHĐ", "ETF", "IPO", "ROE", "ROA", "EPS",
    "HNX", "OTC", "GMT", "UBC", "TOD",
})


def tag_tickers(text: str, watchlist: list[str] | set[str],
                stoplist: frozenset[str] = DEFAULT_STOPLIST) -> list[str]:
    """Trả list mã (theo thứ tự xuất hiện, unique) có trong watchlist, trừ stoplist."""
    if not text:
        return []
    allowed = {t.upper() for t in watchlist} - stoplist
    seen: list[str] = []
    for m in _TICKER_RE.findall(text):
        if m in allowed and m not in seen:
            seen.append(m)
    return seen
