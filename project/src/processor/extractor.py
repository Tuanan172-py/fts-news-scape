"""Extract plain text and main content from HTML source with Trafilatura."""

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
    """Extract article content from a URL or from supplied HTML.

    Args:
        url: Article URL.
        html: Article HTML when already downloaded; None triggers a download from `url`.

    Returns:
        Dict with raw_html, content and the processing status.
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
    """Extract clean text from an HTML fragment or a full page.

    Args:
        html_fragment: HTML fragment or document to extract from.

    Returns:
        Plain text with markup removed.
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
