"""Nhận diện và gán nhãn mã cổ phiếu xuất hiện trong văn bản theo danh sách theo dõi."""

from __future__ import annotations

import re

_TICKER_RE = re.compile(r"\b[A-Z]{3}\b")

# Ngữ cảnh địa danh phía TRƯỚC mã: "TP.HCM", "TP HCM", "Thành phố HCM", "UBND HCM", "khu vực HCM".
LOCATION_LEFT_GUARD_RE = re.compile(
    r"(?:\bT\.?\s*P\.?\s*|\bthành\s+phố\s+|\bUBND\s*|\bkhu\s+vực\s*)$", re.IGNORECASE)
# Ngữ cảnh địa danh phía SAU mã: "HCM City", "HCMC".
LOCATION_RIGHT_GUARD_RE = re.compile(r"^(?:\s*City\b|C\b)")

# Danh sách từ viết hoa 3 chữ cái phổ biến cần loại trừ nhằm giảm thiểu false positive.
DEFAULT_STOPLIST = frozenset({
    "GDP", "CPI", "PMI", "FED", "USD", "EUR", "JPY", "CNY", "VND",
    "CEO", "CFO", "COO", "HHĐ", "ETF", "IPO", "ROE", "ROA", "EPS",
    "HNX", "OTC", "GMT", "UBC", "TOD",
})


def is_location_context(text: str, start: int, end: int) -> bool:
    """Kiểm tra mã 3 ký tự tại vị trí cho trước có nằm trong cụm địa danh hay không.

    Args:
        text: Văn bản gốc chứa mã.
        start: Vị trí bắt đầu của mã trong văn bản.
        end: Vị trí kết thúc của mã trong văn bản.

    Returns:
        True nếu mã là một phần của tên địa danh (ví dụ "TP.HCM"), ngược lại False.
    """
    return bool(LOCATION_LEFT_GUARD_RE.search(text[:start])
                or LOCATION_RIGHT_GUARD_RE.match(text[end:]))


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
    for m in _TICKER_RE.finditer(text):
        code = m.group()
        if code not in allowed or code in seen:
            continue
        if is_location_context(text, m.start(), m.end()):
            continue
        seen.append(code)
    return seen
