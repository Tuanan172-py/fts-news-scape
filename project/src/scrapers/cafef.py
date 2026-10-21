"""Scrape the CafeF source by combining its internal API and per-category RSS feeds."""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import feedparser
from loguru import logger

from src.core.base_scraper import BaseScraper
from src.core.config import load_watchlist
from src.core.models import Article
from src.core.tickers import tag_tickers
from src.processor.extractor import extract_text
from src.scrapers import register
from src.scrapers.capture_mixin import CaptureMixin
from src.scrapers.rss_generic import _clean_title, _decode_feed, _parse_entry_date

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
_DATE_RE = re.compile(r"/Date\((\d+)(?:[+-]\d{4})?\)/")


def parse_cafef_date(raw: str) -> str | None:
    """Parse a CafeF timestamp date string into an ISO 8601 timestamp.

    Args:
        raw: Raw date string of the form '/Date(...)/'.

    Returns:
        ISO 8601 timestamp, or None when the format does not match.
    """
    m = _DATE_RE.search(raw or "")
    if not m:
        return None
    dt = datetime.fromtimestamp(int(m.group(1)) / 1000, tz=VN_TZ)
    return dt.isoformat(timespec="seconds")


@register("cafef")
class CafeFScraper(CaptureMixin, BaseScraper):
    """Scrape CafeF news through the per-ticker API and per-category RSS feeds.

    Attributes:
        endpoint: URL of the Ajax API that lists articles.
        params: API query parameters.
        headers: HTTP headers sent to the API.
        content_selector: CSS selector of the article content area.
        max_details: Maximum number of article details to fetch per cycle.
        watchlist: Stock tickers to watch.
        feeds: Additional category RSS feeds.
    """
    BASE_URL = "https://cafef.vn"

    def __init__(self, config, http, dedup):
        """Initialize the scraper from its source config.

        Args:
            config: Source config dict.
            http: HTTP client.
            dedup: Deduplication cache.
        """
        super().__init__(config, http, dedup)
        api = config.get("api", {})
        self.endpoint = api.get("endpoint",
                                f"{self.BASE_URL}/du-lieu/Ajax/PageNew/News.ashx")
        self.params = api.get("params", {})
        self.headers = api.get("headers", {})
        detail = config.get("detail", {})
        self.content_selector = detail.get("content_selector", "div#mainContent")
        self.max_details = detail.get("max_details_per_cycle", 30)
        self.watchlist = config.get("watchlist") or load_watchlist()
        self.feeds = config.get("rss", {}).get("feeds", [])
        self._details_fetched = 0
        self._init_capture()

    def fetch_list(self) -> list[dict]:
        """Fetch raw articles from the per-ticker API and the category RSS feeds.

        Returns:
            One dict of raw article data per entry.
        """
        self._details_fetched = 0
        items: list[dict] = []
        for sym in self.watchlist:
            data = self.http.get_json(
                self.endpoint,
                params={**self.params, "symbol": sym.lower()},
                referer=f"{self.BASE_URL}/",
                headers=self.headers,
                timeout=self.config.get("timeout", 30),
            )
            if not data:
                self.errors.append(f"list fetch failed for symbol {sym}")
                continue
            rows = data.get("Data") or []
            if not rows and data.get("Success") is False:
                logger.warning("[cafef] {}: {}", sym, data.get("Message"))
                continue
            for it in rows:
                it["_symbol"] = sym
                items.append(it)
        # Per-category RSS branch: adds news not tagged with a ticker.
        for feed_cfg in self.feeds:
            feed_url = feed_cfg["url"]
            feed_name = feed_cfg.get("name", feed_url)
            raw_bytes = self.http.get_bytes(feed_url, timeout=self.config.get("timeout", 30))
            if raw_bytes is None:
                self.errors.append(f"feed fetch failed: {feed_name}")
                continue
            feed = feedparser.parse(_decode_feed(raw_bytes))
            if feed.bozo and not feed.entries:
                self.errors.append(f"feed parse failed: {feed_name}")
                continue
            for e in feed.entries:
                items.append({
                    "_rss": True,
                    "link": (e.get("link") or "").strip(),
                    "title": (e.get("title") or "").strip(),
                    "summary": (e.get("summary") or "").strip(),
                    "author": (e.get("author") or "").strip(),
                    "published_parsed": e.get("published_parsed"),
                    "updated_parsed": e.get("updated_parsed"),
                    "published": e.get("published"),
                    "updated": e.get("updated"),
                    "_feed_name": feed_name,
                })
        return items

    def parse_item(self, raw: dict) -> Article | None:
        """Parse a raw API or RSS record into an Article.

        Args:
            raw: Raw record from an API response or an RSS feed.

        Returns:
            Article, or None when the record is invalid.
        """
        if raw.get("_rss"):
            return self._parse_rss_item(raw)
        title = (raw.get("Title") or "").strip()
        link = (raw.get("LinkDetail") or "").strip()
        if not title or not link:
            logger.warning("[cafef] item missing title/link, skipped")
            return None
        published = parse_cafef_date(raw.get("DeployDate") or "")
        if published is None and raw.get("DeployDate"):
            logger.warning("[cafef] unparseable date: {}", raw["DeployDate"])
        return Article(
            url=urljoin(self.BASE_URL, link),
            title=title,
            source_domain="cafef.vn",
            summary=(raw.get("SubTitle") or "").strip(),
            published_at=published or "",
            symbols=[raw["_symbol"]] if raw.get("_symbol") else [],
            metadata={"image": raw.get("Image", ""),
                      "news_type": raw.get("NewsType")},
        )

    def _parse_rss_item(self, raw: dict) -> Article | None:
        """Parse one category RSS feed record into an Article.

        Args:
            raw: RSS entry data record.

        Returns:
            Article, or None when the URL or title is missing.
        """
        url = raw["link"]
        title = _clean_title(raw["title"])
        if not url or not title:
            return None
        summary_text = extract_text(raw["summary"]) if "<" in raw["summary"] \
            else raw["summary"]
        return Article(
            url=urljoin(self.BASE_URL, url),
            title=title,
            source_domain="cafef.vn",
            summary=summary_text,
            published_at=_parse_entry_date(raw),
            author=raw.get("author", ""),
            symbols=tag_tickers(f"{title} {summary_text}", self.watchlist),
            categories=[raw["_feed_name"]],
            metadata={"feed_name": raw["_feed_name"], "language": "vi"},
        )

    def enrich(self, article: Article) -> None:
        """Download the detail page and store a byte-exact Bronze copy for the article.

        Args:
            article: Article to enrich with detail content.
        """
        if self._details_fetched >= self.max_details:
            article.content_text = article.summary
            article.metadata["detail_deferred"] = True
            return
        html = self._capture_and_extract(article, "cafef.vn",
                                         f"{self.BASE_URL}/", self.content_selector)
        if html is None:
            return
        self._details_fetched += 1
        article.content_text = extract_text(article.content_html) or article.summary
