"""Bóc tách văn bản thuần và nội dung chính từ mã nguồn HTML bằng Trafilatura."""

from __future__ import annotations

import trafilatura
from loguru import logger

_EXTRACT_KW = dict(
    output_format="txt",
    include_tables=True,
    include_images=False,
    include_links=False,
    include_comments=False,
)


def extract_content(url: str, html: str | None = None) -> dict:
    """Trích xuất nội dung bài viết từ địa chỉ URL hoặc chuỗi HTML có sẵn.

    Args:
        url: Địa chỉ URL bài viết.
        html: Chuỗi HTML bài viết nếu đã tải trước.

    Returns:
        Dictionary chứa raw_html, content và trạng thái xử lý status.
    """
    result = {"raw_html": "", "content": "", "status": "ok"}

    if html is None:
        html = trafilatura.fetch_url(url)
        if html is None:
            result["status"] = "fetch_failed"
            return result

    result["raw_html"] = html
    extracted = trafilatura.extract(html, **_EXTRACT_KW)
    if extracted:
        result["content"] = extracted
    else:
        result["status"] = "extract_failed"
        logger.debug("trafilatura extract failed for {}", url)
    return result


def extract_text(html_fragment: str) -> str:
    """Trích xuất văn bản sạch từ một đoạn mã HTML hoặc toàn bộ trang.

    Args:
        html_fragment: Đoạn mã HTML hoặc tài liệu HTML cần bóc tách.

    Returns:
        Chuỗi văn bản thuần đã làm sạch thẻ định dạng.
    """
    if not html_fragment:
        return ""
    text = trafilatura.extract(html_fragment, **_EXTRACT_KW)
    if not text:
        text = trafilatura.extract(f"<html><body>{html_fragment}</body></html>",
                                   **_EXTRACT_KW)
    if not text:
        from bs4 import BeautifulSoup
        text = BeautifulSoup(html_fragment, "lxml").get_text(" ", strip=True)
    return text or ""
