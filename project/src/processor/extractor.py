"""
Content extraction — bóc tách body bài viết.

trafilatura primary. Trả về CẢ raw HTML (spec §9: bảo toàn nguyên bản)
lẫn text sạch.
"""

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
    """Extract nội dung chính từ URL hoặc HTML có sẵn.

    Returns:
        dict: {raw_html, content (text sạch), status}
        status: ok | fetch_failed | extract_failed
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
    """Text sạch từ HTML fragment hoặc full page.

    trafilatura fail trên bare fragment (<div>...) → wrap <html><body>.
    Fallback cuối: BS4 get_text.
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
