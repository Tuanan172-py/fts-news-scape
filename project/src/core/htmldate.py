"""Extract the publication time from a detail-page HTML for articles built from a URL alone."""

from __future__ import annotations

import html as _html
import re
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))

# Ordered by trust. JSON-LD comes last: vietnambiz labels local time as +00:00 there.
_META_PATTERNS = (
    re.compile(r'<meta[^>]+(?:property|name)=["\']article:published_time["\'][^>]*>', re.I),
    re.compile(r'<meta[^>]+itemprop=["\']datePublished["\'][^>]*>', re.I),
    re.compile(r'<meta[^>]+name=["\']pubdate["\'][^>]*>', re.I),
)
_CONTENT = re.compile(r'content=["\']([^"\']+)["\']', re.I)
_JSONLD = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')


def normalize_iso(raw: str) -> str:
    """Normalize a timestamp to ISO 8601 with seconds and an explicit offset.

    A value without an offset is read as Vietnam time, which is what every registered
    source publishes.

    Args:
        raw: Timestamp text, possibly HTML-escaped, with `+0700`, `Z` or no offset.

    Returns:
        ISO timestamp such as `2026-11-11T10:30:00+07:00`, or an empty string when unparseable.
    """
    s = _html.unescape(raw or "").strip().replace(" ", "T", 1)
    if not s:
        return ""
    s = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", s)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=VN_TZ)
    return dt.astimezone(VN_TZ).isoformat(timespec="seconds")


def extract_published_at(page: str | bytes | None) -> str:
    """Return the publication time declared by a detail page.

    Args:
        page: HTML of the article page.

    Returns:
        ISO timestamp in Vietnam time, or an empty string when the page declares none.
    """
    if not page:
        return ""
    if isinstance(page, bytes):
        page = page.decode("utf-8", errors="replace")
    head = page[:200_000]
    for pattern in _META_PATTERNS:
        for tag in pattern.findall(head):
            m = _CONTENT.search(tag)
            value = normalize_iso(m.group(1)) if m else ""
            if value:
                return value
    m = _JSONLD.search(head)
    return normalize_iso(m.group(1)) if m else ""
