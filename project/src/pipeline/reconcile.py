"""Đối chiếu độc lập kho bài với sitemap của nguồn và ghi độ phủ thu thập (rule 10)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Callable
from urllib.parse import urlsplit

from loguru import logger

from src.core.urlnorm import url_key
from src.db import registry

VN_TZ = timezone(timedelta(hours=7))
Fetch = Callable[[str], str | None]

# Nguồn có sitemap dùng được. Nguồn không nằm trong bảng này (vietstock, vietnambiz,
# thoibaotaichinhvietnam) chưa có kênh đối chiếu độc lập và được radar ghi rõ là "không có".
REFERENCE_DOMAINS = ("baodautu.vn", "tinnhanhchungkhoan.vn", "cafef.vn", "vneconomy.vn")

_CAFEF_WINDOW = re.compile(r"sitemaps-(\d{4})-(\d{1,2})-(\d{1,2})-(\d{1,2})\.xml$")


def parse_urlset(xml: str) -> list[tuple[str, str]]:
    """Trích các cặp (loc, lastmod) từ một sitemap dạng urlset hoặc sitemapindex.

    Args:
        xml: Nội dung XML của sitemap.

    Returns:
        Danh sách (url, lastmod); lastmod là chuỗi rỗng khi sitemap không khai báo.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    out: list[tuple[str, str]] = []
    for node in root:
        loc = lastmod = ""
        for child in node:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "loc":
                loc = (child.text or "").strip()
            elif tag == "lastmod":
                lastmod = (child.text or "").strip()
        if loc:
            out.append((loc, lastmod))
    return out


def _month_days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def sitemap_urls(domain: str, start: date, end: date, fetch: Fetch) -> list[str]:
    """Liệt kê URL sitemap bài viết của một nguồn cho khoảng ngày cần đối chiếu.

    Args:
        domain: Tên miền nguồn nằm trong REFERENCE_DOMAINS.
        start: Ngày đầu của khoảng.
        end: Ngày cuối của khoảng.
        fetch: Hàm tải văn bản từ URL, trả None khi lỗi.

    Returns:
        Danh sách URL sitemap cần tải.
    """
    months = sorted({(d.year, d.month) for d in _month_days(start, end)})
    if domain == "baodautu.vn":
        return [f"https://baodautu.vn/sitemaps/news-{y}-{m}.xml" for y, m in months]
    if domain == "tinnhanhchungkhoan.vn":
        return [f"https://www.tinnhanhchungkhoan.vn/sitemaps/news-{y}-{m}.xml" for y, m in months]
    if domain == "vneconomy.vn":
        return ["https://vneconomy.vn/sitemap/latest-news.xml"]
    if domain == "cafef.vn":
        urls = ["https://cafef.vn/latest-news-sitemap.xml"]
        index = fetch("https://cafef.vn/sitemap.xml")
        for loc, _ in parse_urlset(index or ""):
            m = _CAFEF_WINDOW.search(loc)
            if not m:
                continue
            y, mo, d1, d2 = (int(g) for g in m.groups())
            try:
                lo, hi = date(y, mo, d1), date(y, mo, min(d2, 28)) + timedelta(days=max(d2 - 28, 0))
            except ValueError:
                continue
            if hi >= start and lo <= end:
                urls.append(loc)
        return urls
    return []


def _is_article_loc(loc: str) -> bool:
    return len(urlsplit(loc).path.strip("/")) > 0


def _day_of(lastmod: str, today: date) -> str:
    return lastmod[:10] if len(lastmod) >= 10 else today.isoformat()


def collect_reference(domain: str, start: date, end: date, fetch: Fetch,
                      today: date | None = None) -> dict[str, dict[str, str]]:
    """Gom URL bài từ sitemap của nguồn, nhóm theo ngày.

    Args:
        domain: Tên miền nguồn.
        start: Ngày đầu của khoảng.
        end: Ngày cuối của khoảng.
        fetch: Hàm tải văn bản từ URL.
        today: Ngày dùng cho mục không có lastmod; mặc định là hôm nay theo giờ VN.

    Returns:
        Ánh xạ ngày ISO sang {khoá bài: URL}; chỉ gồm ngày nằm trong khoảng.
    """
    today = today or datetime.now(VN_TZ).date()
    by_day: dict[str, dict[str, str]] = defaultdict(dict)
    for sm in sitemap_urls(domain, start, end, fetch):
        xml = fetch(sm)
        if not xml:
            logger.warning("[reconcile] không tải được {}", sm)
            continue
        for loc, lastmod in parse_urlset(xml):
            if not _is_article_loc(loc):
                continue
            day = _day_of(lastmod, today)
            if not (start.isoformat() <= day <= end.isoformat()):
                continue
            key = url_key(loc)
            if key:
                by_day[day].setdefault(key, loc)
    return by_day


def reconcile(conn, fetch: Fetch, *, domains: tuple[str, ...] = REFERENCE_DOMAINS,
              days: int = 3, today: date | None = None) -> dict[str, dict[str, dict]]:
    """Đối chiếu kho với sitemap, ghi URL thiếu vào sổ phát hiện và cập nhật độ phủ.

    Args:
        conn: Kết nối ghi tới DB vận hành, row_factory là sqlite3.Row hoặc tuple.
        fetch: Hàm tải văn bản từ URL, trả None khi lỗi.
        domains: Các nguồn cần đối chiếu.
        days: Số ngày gần nhất cần đối chiếu, tính cả hôm nay.
        today: Ngày hiện tại theo giờ VN; mặc định lấy từ đồng hồ.

    Returns:
        Ánh xạ nguồn sang ngày sang {ref_n, in_db_n, missing_n}.
    """
    today = today or datetime.now(VN_TZ).date()
    start = today - timedelta(days=days - 1)
    since = (start - timedelta(days=3)).isoformat()
    have: set[str] = set()
    for (url,) in conn.execute(
            "SELECT url FROM articles WHERE substr(fetched_at,1,10) >= ?", (since,)):
        k = url_key(url)
        if k:
            have.add(k)
    for (k,) in conn.execute(
            "SELECT url_canonical FROM discovered_urls WHERE state IN ('captured','gone')"):
        have.add(k)

    now = datetime.now(VN_TZ).isoformat(timespec="seconds")
    report: dict[str, dict[str, dict]] = {}
    for domain in domains:
        ref = collect_reference(domain, start, today, fetch, today)
        report[domain] = {}
        for day, items in sorted(ref.items()):
            missing = {k: u for k, u in items.items() if k not in have}
            for k, u in missing.items():
                registry.discover(conn, u, domain, "reconcile")
            stats = {"ref_n": len(items), "in_db_n": len(items) - len(missing),
                     "missing_n": len(missing)}
            report[domain][day] = stats
            conn.execute(
                "INSERT INTO capture_coverage (day, source_domain, ref_n, in_db_n, missing_n, "
                "backfilled_n, checked_at) VALUES (?, ?, ?, ?, ?, 0, ?) "
                "ON CONFLICT(day, source_domain) DO UPDATE SET ref_n=excluded.ref_n, "
                "in_db_n=excluded.in_db_n, missing_n=excluded.missing_n, "
                "checked_at=excluded.checked_at",
                (day, domain, stats["ref_n"], stats["in_db_n"], stats["missing_n"], now))
        backfilled = conn.execute(
            "SELECT COUNT(*) FROM discovered_urls WHERE first_seen_via='reconcile' "
            "AND state='captured' AND source_domain=?", (domain,)).fetchone()[0]
        conn.execute("UPDATE capture_coverage SET backfilled_n=? WHERE source_domain=? AND day>=?",
                     (backfilled, domain, start.isoformat()))
    conn.commit()
    return report
