"""Nhận diện và gán nhãn mã cổ phiếu xuất hiện trong văn bản theo danh sách theo dõi."""

from __future__ import annotations

import re

_TICKER_RE = re.compile(r"\b[A-Z]{3}\b")

# Danh sách từ viết hoa 3 chữ cái phổ biến cần loại trừ nhằm giảm thiểu false positive.
DEFAULT_STOPLIST = frozenset({
    "GDP", "CPI", "PMI", "FED", "USD", "EUR", "JPY", "CNY", "VND",
    "CEO", "CFO", "COO", "HHĐ", "ETF", "IPO", "ROE", "ROA", "EPS",
    "HNX", "OTC", "GMT", "UBC", "TOD",
})


def tag_tickers(text: str, watchlist: list[str] | set[str],
                stoplist: frozenset[str] = DEFAULT_STOPLIST) -> list[str]:
    """Trích xuất danh sách mã cổ phiếu duy nhất xuất hiện trong văn bản.

    Args:
        text: Đoạn văn bản cần tìm mã cổ phiếu.
        watchlist: Danh sách hoặc tập hợp mã cổ phiếu được theo dõi.
        stoplist: Tập hợp từ viết hoa 3 chữ cái cần loại trừ.

    Returns:
        Danh sách mã cổ phiếu hợp lệ theo thứ tự xuất hiện đầu tiên.
    """
    if not text:
        return []
    allowed = {t.upper() for t in watchlist} - stoplist
    seen: list[str] = []
    for m in _TICKER_RE.findall(text):
        if m in allowed and m not in seen:
            seen.append(m)
    return seen
