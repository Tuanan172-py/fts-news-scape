"""Normalize article URLs to a stable identity key across URL variants."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAMS = frozenset({
    "fbclid", "gclid", "mc_cid", "mc_eid", "zarsrc", "ref", "ref_src", "igshid", "_ga",
})
_TRACKING_PREFIXES = ("utm_",)

# Article IDs issued by the source itself stay stable even when the slug changes with the title.
_SOURCE_ID_PATTERNS = (
    ("cafef.vn", re.compile(r"-(\d{14,20})\.chn(?:$|\?)")),
    ("baodautu.vn", re.compile(r"-d(\d{3,})\.html(?:$|\?)")),
    ("vietnambiz.vn", re.compile(r"-(\d{12,18})\.htm(?:$|\?)")),
    ("vietstock.vn", re.compile(r"-(\d{6,9})\.htm(?:$|\?)")),
    ("tinnhanhchungkhoan.vn", re.compile(r"-post(\d+)(?:\.html)?(?:$|\?)")),
    ("thoibaotaichinhvietnam.vn", re.compile(r"-(\d{5,8})\.html(?:$|\?)")),
    ("fireant.vn", re.compile(r"/dashboard/content/(\d+)(?:$|\?)")),
)


def canonical_url(url: str) -> str:
    """Reduce a URL to canonical form without tracking parameters, fragment, `www.` or trailing `/`, using the https scheme.

    Args:
        url: Article URL in any form.

    Returns:
        Canonical URL; an empty string if the input is empty.
    """
    url = (url or "").strip()
    if not url:
        return ""
    parts = urlsplit(url)
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in _TRACKING_PARAMS
             and not k.lower().startswith(_TRACKING_PREFIXES)]
    query.sort()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, urlencode(query), ""))


def url_key(url: str) -> str:
    """Return the article identity key: the source article ID if recognized, otherwise the canonical URL.

    Args:
        url: Article URL.

    Returns:
        String `<domain>#<article id>` or the canonical URL. Empty if the URL is empty.
    """
    canon = canonical_url(url)
    if not canon:
        return ""
    host = urlsplit(canon).netloc
    for domain, pattern in _SOURCE_ID_PATTERNS:
        if host.endswith(domain):
            m = pattern.search(canon)
            if m:
                return f"{domain}#{m.group(1)}"
    return canon
