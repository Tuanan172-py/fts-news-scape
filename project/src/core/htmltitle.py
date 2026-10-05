"""Trích tiêu đề bài từ HTML trang chi tiết và kiểm tra tiêu đề hợp lệ."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

MIN_TITLE_CHARS = 8
_SITE_SUFFIX = re.compile(r"\s*[|–—-]\s*(?:[^|–—-]{2,40})$")


def is_valid_title(title: str) -> bool:
    """Kiểm tra tiêu đề đủ dài và không chỉ gồm chữ số hay ký hiệu.

    Args:
        title: Tiêu đề cần kiểm tra.

    Returns:
        True nếu tiêu đề dùng được làm khoá băm và hiển thị.
    """
    t = (title or "").strip()
    return len(t) >= MIN_TITLE_CHARS and any(ch.isalpha() for ch in t)


def extract_page_title(html: str) -> str:
    """Lấy tiêu đề bài từ `og:title`, rồi `<h1>`, rồi `<title>` đã bỏ hậu tố tên báo.

    Args:
        html: Mã nguồn HTML trang chi tiết.

    Returns:
        Tiêu đề hợp lệ đầu tiên tìm được, hoặc chuỗi rỗng.
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    candidates: list[str] = []
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        candidates.append(og["content"])
    h1 = soup.find("h1")
    if h1:
        candidates.append(h1.get_text(" ", strip=True))
    if soup.title and soup.title.string:
        candidates.append(_SITE_SUFFIX.sub("", soup.title.string.strip()))
    for c in candidates:
        c = re.sub(r"\s+", " ", c).strip()
        if is_valid_title(c):
            return c
    return ""
