"""Extract the article title from a detail-page HTML and validate titles."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

MIN_TITLE_CHARS = 8
_SITE_SUFFIX = re.compile(r"\s*[|–—-]\s*(?:[^|–—-]{2,40})$")


def is_valid_title(title: str) -> bool:
    """Check that a title is long enough and not made only of digits or symbols.

    Args:
        title: Title to check.

    Returns:
        True if the title is usable as a hash key and for display.
    """
    t = (title or "").strip()
    return len(t) >= MIN_TITLE_CHARS and any(ch.isalpha() for ch in t)


def extract_page_title(html: str) -> str:
    """Extract the title from `og:title`, then `<h1>`, then `<title>` with the site-name suffix removed.

    Args:
        html: HTML source of the detail page.

    Returns:
        First valid title found, or an empty string.
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
