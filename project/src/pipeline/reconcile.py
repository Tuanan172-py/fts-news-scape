"""Reconcile the article store against source sitemaps independently and record capture coverage (rule 10)."""

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

# Sources with an independent reference channel: a sitemap, or for vietnambiz the dated
# section listings. fireant.vn has none; its API pages back to a catch-up cutoff instead
# (src/core/catchup.py).
REFERENCE_DOMAINS = ("baodautu.vn", "tinnhanhchungkhoan.vn", "cafef.vn", "vneconomy.vn",
                     "thoibaotaichinhvietnam.vn", "vietstock.vn", "vietnambiz.vn")
# Minimum minutes between two reconciliations of one domain, on top of the caller's interval.
# The vietstock sitemap is one 37 MB file without compression.
REFERENCE_EVERY_MINUTES = {"vietstock.vn": 360, "vietnambiz.vn": 120}
# Reference URLs that are not news: vietstock category 4511 is paid PR.
REFERENCE_EXCLUDE = {"vietstock.vn": re.compile(r"-4511-\d+\.htm$")}
# Request timeout in seconds for reference documents slower than the default 30 s.
REFERENCE_TIMEOUT = {"vietstock.vn": 240}
# vietnambiz sections, matching the RSS feeds the scraper reads.
VIETNAMBIZ_SECTIONS = ("chung-khoan", "tai-chinh", "vi-mo", "doanh-nghiep", "nha-dat", "hang-hoa")
VIETNAMBIZ_MAX_PAGES = 40
# baodautu: monthly sitemaps return "Not found act function sitemap_month" since 2026-10-23,
# so its category listings are the reference. Listings carry no date: the day comes from the
# store for known URLs and from the detail page for the few unknown ones.
BAODAUTU_MAX_PAGES = 6
BAODAUTU_MAX_DETAIL = 40
_BDT_LINK = re.compile(r'href="(?:https://baodautu\.vn)?(/[a-z0-9-]+-d\d+\.html)"')
_VNB_LINK = re.compile(r'href="(?:https://vietnambiz\.vn)?(/[a-z0-9-]+-\d{12,}\.htm)"')
_VNB_IMG_DAY = re.compile(r"/images/(\d{4})/(\d{1,2})/(\d{1,2})/")
_VNB_TIME = re.compile(r'need-get-timeago"\s+title="(\d{4}-\d{2}-\d{2})T')
_FAST_URL = re.compile(r"<url>\s*<loc>\s*([^<\s]+)\s*</loc>(?:\s*<lastmod>\s*([^<\s]*)\s*</lastmod>)?")
_FAST_PARSE_BYTES = 2_000_000

_CAFEF_WINDOW = re.compile(r"sitemaps-(\d{4})-(\d{1,2})-(\d{1,2})-(\d{1,2})\.xml$")


def parse_urlset(xml: str) -> list[tuple[str, str]]:
    """Extract (loc, lastmod) pairs from a urlset or sitemapindex sitemap.

    Args:
        xml: XML content of the sitemap.

    Returns:
        List of (url, lastmod); lastmod is an empty string when the sitemap omits it.
    """
    if len(xml) > _FAST_PARSE_BYTES:
        # ElementTree on the 37 MB vietstock sitemap costs seconds and hundreds of MB.
        return [(loc, lastmod or "") for loc, lastmod in _FAST_URL.findall(xml)]
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
    """Return every date from start to end inclusive."""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def sitemap_urls(domain: str, start: date, end: date, fetch: Fetch) -> list[str]:
    """List the article sitemap URLs of a source for the date range to reconcile.

    Args:
        domain: Source domain listed in REFERENCE_DOMAINS.
        start: First day of the range.
        end: Last day of the range.
        fetch: Function that downloads text from a URL, returning None on failure.

    Returns:
        Sitemap URLs to download.
    """
    months = sorted({(d.year, d.month) for d in _month_days(start, end)})
    if domain == "baodautu.vn":
        return [f"https://baodautu.vn/sitemaps/news-{y}-{m}.xml" for y, m in months]
    if domain == "tinnhanhchungkhoan.vn":
        return [f"https://www.tinnhanhchungkhoan.vn/sitemaps/news-{y}-{m}.xml" for y, m in months]
    if domain == "vneconomy.vn":
        return ["https://vneconomy.vn/sitemap/latest-news.xml"]
    if domain == "thoibaotaichinhvietnam.vn":
        return [f"https://thoibaotaichinhvietnam.vn/stores/lookssitemaps/site_1/sitemap-month-{y}-{m}.xml"
                for y, m in months]
    if domain == "vietstock.vn":
        return ["https://vietstock.vn/sitemap.xml"]
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
    """Return True if the URL has a non-empty path."""
    return len(urlsplit(loc).path.strip("/")) > 0


def _day_of(lastmod: str, today: date) -> str:
    """Return the ISO day of lastmod, or today's ISO date when lastmod is missing."""
    return lastmod[:10] if len(lastmod) >= 10 else today.isoformat()


def collect_reference(domain: str, start: date, end: date, fetch: Fetch,
                      today: date | None = None) -> dict[str, dict[str, str]]:
    """Collect article URLs from a source sitemap, grouped by day.

    Args:
        domain: Source domain.
        start: First day of the range.
        end: Last day of the range.
        fetch: Function that downloads text from a URL.
        today: Day used for entries without lastmod; defaults to today in VN time.

    Returns:
        Mapping of ISO day to {article key: URL}; only days inside the range.
    """
    today = today or datetime.now(VN_TZ).date()
    if domain == "vietnambiz.vn":
        return collect_vietnambiz(start, end, fetch)
    by_day: dict[str, dict[str, str]] = defaultdict(dict)
    skip = REFERENCE_EXCLUDE.get(domain)
    for sm in sitemap_urls(domain, start, end, fetch):
        xml = fetch(sm)
        if not xml:
            logger.warning("[reconcile] không tải được {}", sm)
            continue
        for loc, lastmod in parse_urlset(xml):
            if not _is_article_loc(loc) or (skip and skip.search(loc)):
                continue
            day = _day_of(lastmod, today)
            if not (start.isoformat() <= day <= end.isoformat()):
                continue
            key = url_key(loc)
            if key:
                by_day[day].setdefault(key, loc)
    return by_day


def parse_vietnambiz_listing(html: str) -> list[tuple[str, str]]:
    """Extract (article URL, ISO day) pairs from the main list of a vietnambiz section page.

    Only `div.list-news` items count; featured and sidebar blocks repeat other days. The day
    comes from the item's timestamp, else from the thumbnail upload path `/images/YYYY/MM/DD/`.

    Args:
        html: HTML of the section page.

    Returns:
        Pairs in page order; items without a link or a day are skipped.
    """
    from bs4 import BeautifulSoup

    out: list[tuple[str, str]] = []
    for item in BeautifulSoup(html or "", "lxml").select("div.list-news div.item"):
        block = str(item)
        link = _VNB_LINK.search(block)
        stamp = _VNB_TIME.search(block)
        day = stamp.group(1) if stamp else ""
        if not day:
            img = _VNB_IMG_DAY.search(block)
            if img:
                try:
                    day = date(*(int(g) for g in img.groups())).isoformat()
                except ValueError:
                    day = ""
        if link and day:
            out.append((f"https://vietnambiz.vn{link.group(1)}", day))
    return out


def collect_vietnambiz(start: date, end: date, fetch: Fetch,
                       max_pages: int = VIETNAMBIZ_MAX_PAGES) -> dict[str, dict[str, str]]:
    """Collect vietnambiz article URLs by day from its section listings.

    vietnambiz publishes no sitemap. Each section pages back in time, so reading until a
    whole page is older than `start` lists every article of the window.

    Args:
        start: First day of the range.
        end: Last day of the range.
        fetch: Function that downloads text from a URL.
        max_pages: Safety cap on pages per section.

    Returns:
        Mapping of ISO day to {article key: URL}.
    """
    by_day: dict[str, dict[str, str]] = defaultdict(dict)
    lo, hi = start.isoformat(), end.isoformat()
    for section in VIETNAMBIZ_SECTIONS:
        for page in range(1, max_pages + 1):
            url = f"https://vietnambiz.vn/{section}/trang-{page}.htm"
            items = parse_vietnambiz_listing(fetch(url) or "")
            if not items:
                if page == 1:
                    logger.warning("[reconcile] vietnambiz {}: trang 1 không có bài", section)
                break
            for loc, day in items:
                key = url_key(loc)
                if key and lo <= day <= hi:
                    by_day[day].setdefault(key, loc)
            if max(day for _, day in items) < lo:
                break
    return by_day


def collect_baodautu(start: date, end: date, fetch: Fetch, known_day: dict[str, str], *,
                     max_pages: int = BAODAUTU_MAX_PAGES,
                     max_detail: int = BAODAUTU_MAX_DETAIL) -> dict[str, dict[str, str]]:
    """Collect baodautu article URLs by day from its category listings.

    Args:
        start: First day of the range.
        end: Last day of the range.
        fetch: Function that downloads text from a URL.
        known_day: Article key to ISO day for articles already in the store.
        max_pages: Safety cap on pages per category.
        max_detail: Cap on detail pages fetched to date unknown URLs in one run.

    Returns:
        Mapping of ISO day to {article key: URL}.
    """
    from src.core.config import load_domain_config
    from src.scrapers.baodautu import _parse_detail_date

    cfg = load_domain_config("baodautu")
    cats = (cfg.get("listing") or {}).get("categories") or []
    scope = (cfg.get("detail") or {}).get("date_scope_selector", "span.post-time")
    by_day: dict[str, dict[str, str]] = defaultdict(dict)
    lo, hi = start.isoformat(), end.isoformat()
    seen: set[str] = set()
    details = 0
    for cat in cats:
        for page in range(1, max_pages + 1):
            url = (f"https://baodautu.vn/{cat['slug']}-d{cat['id']}/" if page == 1
                   else f"https://baodautu.vn/{cat['slug']}-d{cat['id']}/p{page}")
            links = list(dict.fromkeys(_BDT_LINK.findall(fetch(url) or "")))
            if not links:
                if page == 1:
                    logger.warning("[reconcile] baodautu {}: trang 1 không có bài", cat["slug"])
                break
            days: list[str] = []
            for path in links:
                loc = f"https://baodautu.vn{path}"
                key = url_key(loc)
                if not key or key in seen:
                    continue
                seen.add(key)
                day = known_day.get(key, "")
                if not day and details < max_detail:
                    details += 1
                    day = _parse_detail_date(fetch(loc) or "", scope)[:10]
                if not day:
                    continue
                days.append(day)
                if lo <= day <= hi:
                    by_day[day].setdefault(key, loc)
            if days and max(days) < lo:
                break
    if details >= max_detail:
        logger.warning("[reconcile] baodautu: chạm trần {} trang chi tiết", max_detail)
    return by_day


def reconcile(conn, fetch: Fetch, *, domains: tuple[str, ...] = REFERENCE_DOMAINS,
              days: int = 3, today: date | None = None) -> dict[str, dict[str, dict]]:
    """Reconcile the store with sitemaps, record missing URLs in the discovery ledger and update coverage.

    Args:
        conn: Write connection to the operational DB; row_factory is sqlite3.Row or tuple.
        fetch: Function that downloads text from a URL, returning None on failure.
        domains: Sources to reconcile.
        days: Number of most recent days to reconcile, including today.
        today: Current day in VN time; defaults to the clock.

    Returns:
        Mapping of source to day to {ref_n, in_db_n, missing_n}.
    """
    today = today or datetime.now(VN_TZ).date()
    start = today - timedelta(days=days - 1)
    since = (start - timedelta(days=3)).isoformat()
    have: set[str] = set()
    known_day: dict[str, str] = {}
    for url, day in conn.execute(
            "SELECT url, substr(COALESCE(NULLIF(published_at, ''), fetched_at), 1, 10) "
            "FROM articles WHERE substr(fetched_at,1,10) >= ?", (since,)):
        k = url_key(url)
        if k:
            have.add(k)
            known_day[k] = day or ""
    for (k,) in conn.execute(
            "SELECT url_canonical FROM discovered_urls WHERE state IN ('captured','gone')"):
        have.add(k)

    now = datetime.now(VN_TZ).isoformat(timespec="seconds")
    report: dict[str, dict[str, dict]] = {}
    for domain in domains:
        ref = collect_reference(domain, start, today, fetch, today)
        if not ref and domain == "baodautu.vn":
            # The sitemap returns an error page since 2026-10-23; fall back to the listings,
            # and return to the sitemap by itself once the source fixes it.
            # Listing pages reach weeks back; dating those URLs from the store avoids detail fetches.
            for url, day in conn.execute(
                    "SELECT url, substr(COALESCE(NULLIF(published_at, ''), fetched_at), 1, 10) "
                    "FROM articles WHERE source_domain = ? AND substr(fetched_at,1,10) >= ?",
                    (domain, (start - timedelta(days=30)).isoformat())):
                k = url_key(url)
                if k:
                    known_day.setdefault(k, day or "")
            ref = collect_baodautu(start, today, fetch, known_day)
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
