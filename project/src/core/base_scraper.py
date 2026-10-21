"""Define the abstract scrape workflow as a Template Method."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from urllib.parse import urlsplit

from loguru import logger

from src.core.htmltitle import extract_page_title
from src.core.models import Article, ScrapeResult, now_vn_iso
from src.crawler.http_client import HTTPClient
from src.db.dedup import DedupCache


class BaseScraper(ABC):
    """Abstract base class of all scrapers.

    Attributes:
        config: Scraper configuration.
        name: Scraper name.
        http: HTTP client used for network requests.
        dedup: Cache used for duplicate checks.
        errors: Errors recorded in the current cycle.
        disabled: True when collection is paused.
    """

    def __init__(self, config: dict, http: HTTPClient, dedup: DedupCache):
        """Initialize the scraper from its configuration and shared services.

        Args:
            config: Scraper configuration; `name` is required.
            http: HTTP client used for network requests.
            dedup: Cache used for duplicate checks.
        """
        self.config = config
        self.name: str = config["name"]
        self.http = http
        self.dedup = dedup
        self.errors: list[str] = []
        self.disabled: bool = not config.get("enabled", True)

    def run(self) -> ScrapeResult:
        """Run one scrape cycle through the standard steps.

        Returns:
            ScrapeResult with the new articles and the error statistics.
        """
        self.errors = []
        started = time.monotonic()
        if self.disabled:
            logger.info("[{}] disabled, skipping", self.name)
            return ScrapeResult(scraper=self.name)

        try:
            raw_items = self.fetch_list()
        except Exception as e:
            logger.error("[{}] fetch_list failed: {}", self.name, e)
            self.errors.append(f"fetch_list: {e}")
            raw_items = []

        articles: list[Article] = []
        for raw in raw_items:
            try:
                a = self.parse_item(raw)
            except Exception as e:
                logger.warning("[{}] parse_item failed: {}", self.name, e)
                self.errors.append(f"parse_item: {e}")
                continue
            if a:
                articles.append(a)

        # Rule 10 (ADR 0013): record discovery BEFORE any filter and drop only technical copies.
        # Semantic duplicates belong to the clustering step after Bronze; never drop an article here.
        via = self.config.get("discovery_via", "listing")
        new = []
        seen_keys: set[str] = set()
        for a in articles:
            key, _is_new, alias_form = self.dedup.discover(a.url, a.source_domain or self.name, via)
            # A seen hash skips the article only when the discovery ledger confirms it reached the store.
            # An article marked seen but without an `articles` row (old silent filter) is fetched again.
            if self.dedup.is_duplicate(a.url, a.title) and (not key or self.dedup.is_captured(key)):
                continue
            if key and (key in seen_keys or (alias_form and self.dedup.is_captured(key))):
                logger.debug("[{}] url alias skipped: {}", self.name, a.url[:80])
                continue
            if key:
                seen_keys.add(key)
            new.append(a)

        for a in new:
            try:
                self.enrich(a)
            except Exception as e:
                logger.warning("[{}] enrich failed for {}: {}", self.name, a.url, e)
                self.errors.append(f"enrich {a.url}: {e}")
            a.processed_at = now_vn_iso()
            # The seen mark is written in the same transaction that stores the article.

        duration = time.monotonic() - started
        logger.info("[{}] cycle done: fetched={} new={} errors={} in {:.1f}s",
                    self.name, len(raw_items), len(new), len(self.errors), duration)
        return ScrapeResult(scraper=self.name, fetched=len(raw_items),
                            new=new, errors=list(self.errors), duration_s=duration)

    @abstractmethod
    def fetch_list(self) -> list[dict]:
        """Fetch the raw records from the data source.

        Returns:
            Raw records as dicts.
        """

    @abstractmethod
    def parse_item(self, raw: dict) -> Article | None:
        """Parse one raw record into an Article.

        Args:
            raw: Raw record collected from the source.

        Returns:
            The parsed Article, or None if the record is invalid.
        """

    def enrich(self, article: Article) -> None:
        """Add detail content to an article from the source page.

        Args:
            article: Article to enrich in place.
        """

    def article_from_url(self, url: str) -> Article | None:
        """Build a minimal Article from a URL by reading the detail-page title.

        Args:
            url: Article URL supplied by the discovery ledger or a reconciliation channel.

        Returns:
            Article with a valid title, or None if the page cannot be fetched or no title is found.
        """
        host = urlsplit(url).netloc.lower().removeprefix("www.")
        html = self.http.get(url, referer=f"https://{host}/",
                             timeout=self.config.get("timeout", 30))
        if not html:
            return None
        title = extract_page_title(html)
        if not title:
            return None
        return Article(url=url, title=title, source_domain=host,
                       metadata={"language": self.config.get("language", "vi"),
                                 "backfill": True})

    def backfill_url(self, url: str) -> Article | None:
        """Scrape one article by URL through this scraper's own enrich and Bronze path.

        Args:
            url: Article URL to fetch.

        Returns:
            Article with enriched content and `processed_at`, or None if the article cannot be built.
        """
        article = self.article_from_url(url)
        if article is None:
            return None
        if hasattr(self, "_details_fetched"):
            self._details_fetched = 0
        try:
            self.enrich(article)
        except Exception as e:
            logger.warning("[{}] backfill enrich failed for {}: {}", self.name, url, e)
            self.errors.append(f"backfill enrich {url}: {e}")
        article.processed_at = now_vn_iso()
        return article
