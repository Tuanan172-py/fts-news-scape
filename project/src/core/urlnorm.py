"""Chuẩn hoá URL bài viết về khoá định danh ổn định giữa các dạng biến thể."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAMS = frozenset({
    "fbclid", "gclid", "mc_cid", "mc_eid", "zarsrc", "ref", "ref_src", "igshid", "_ga",
})
_TRACKING_PREFIXES = ("utm_",)

# Mã bài do chính nguồn cấp: ổn định ngay cả khi slug đổi theo tiêu đề.
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
    """Rút URL về dạng chuẩn: bỏ tham số theo dõi, fragment, `www.`, dấu `/` cuối và đưa scheme về https.

    Args:
        url: URL bài viết ở bất kỳ dạng nào.

    Returns:
        URL chuẩn hoá; chuỗi rỗng nếu đầu vào rỗng.
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
    """Trả khoá định danh bài: mã bài của nguồn nếu nhận ra, ngược lại URL chuẩn hoá.

    Args:
        url: URL bài viết.

    Returns:
        Chuỗi `<domain>#<mã bài>` hoặc URL chuẩn hoá. Rỗng nếu URL rỗng.
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
