"""Scrape VNDirect (vndirect.com.vn) news through the public VNDirect JSON API."""

from __future__ import annotations

from loguru import logger

from src.core.base_scraper import BaseScraper
from src.core.models import Article
from src.processor.extractor import extract_text
from src.scrapers import register


@register("vndirect")
class VndirectScraper(BaseScraper):
    """Scrape news through the VNDirect REST API.

    Attributes:
        API_URL: Default URL of the VNDirect news API.
        api_url: API endpoint URL after configuration.
        page_size: Number of news records fetched per page.
        news_groups: News groups to filter by.
        max_details: Maximum number of articles whose extended content is downloaded when missing.
    """

    API_URL = "https://api-finfo.vndirect.com.vn/v4/news"

    def __init__(self, config, http, dedup):
        """Initialize the scraper from its source config.

        Args:
            config: Source config dict.
            http: HTTP client.
            dedup: Deduplication cache.
        """
        super().__init__(config, http, dedup)
        api = config.get("api", {})
        self.api_url = api.get("endpoint", self.API_URL)
        self.page_size = api.get("page_size", 60)
        self.news_groups = api.get("news_groups", [])
        self.max_details = config.get("detail", {}).get("max_details_per_cycle", 20)
        self._details_fetched = 0

    def fetch_list(self) -> list[dict]:
        """Collect the news list from the VNDirect REST API.

        Returns:
            One dict of raw news data per record.
        """
        self._details_fetched = 0
        params = {"size": self.page_size, "sort": "newsDate:desc"}
        if self.news_groups:
            params["q"] = "newsGroup:" + ",".join(self.news_groups)
        data = self.http.get_json(self.api_url, params=params,
                                  timeout=self.config.get("timeout", 30))
        if not data:
            self.errors.append("news API fetch failed")
            return []
        return data.get("data") or []

    def parse_item(self, raw: dict) -> Article | None:
        """Convert a VNDirect API news record into an Article.

        Args:
            raw: Raw news record dict from the API.

        Returns:
            Valid Article, or None when the title or link is missing.
        """
        title = (raw.get("newsTitle") or "").strip()
        url = (raw.get("newsUrl") or raw.get("dstockUrl") or "").strip()
        if not title or not url:
            logger.warning("[vndirect] item missing title/url, skipped")
            return None
        date, time_ = raw.get("newsDate", ""), raw.get("newsTime", "00:00:00")
        published = f"{date}T{time_}+07:00" if date else ""
        symbols = [s.strip().upper() for s in (raw.get("tagCodes") or "").split(",")
                   if s.strip()]
        group = raw.get("newsGroup", "")
        return Article(
            url=url,
            title=title,
            source_domain="vndirect.com.vn",
            summary=(raw.get("newsAbstract") or "").strip(),
            published_at=published,
            symbols=symbols,
            categories=[group] if group else [],
            metadata={"news_id": raw.get("newsId", ""),
                      "news_source": raw.get("newsSource", ""),
                      "dstock_url": raw.get("dstockUrl", ""),
                      "_content_html": raw.get("newsContent") or ""},
        )

    def enrich(self, article: Article) -> None:
        """Add detail text content to the article.

        When the content is absent from the list response, download it from the original URL.

        Args:
            article: Article to enrich.
        """
        content_html = article.metadata.pop("_content_html", "")
        if content_html:
            article.content_html = content_html
            article.content_text = extract_text(content_html) or article.summary
            if len(article.content_text) >= 200:
                return
        if self._details_fetched >= self.max_details:
            article.content_text = article.content_text or article.summary
            article.metadata["detail_deferred"] = True
            return
        self._details_fetched += 1
        html = self.http.get(article.url, timeout=self.config.get("timeout", 30))
        if html is None:
            article.content_text = article.content_text or article.summary
            return
        from src.processor.extractor import extract_content
        result = extract_content(article.url, html=html)
        if result["content"]:
            article.content_html = article.content_html or result["raw_html"]
            article.content_text = result["content"]
        else:
            article.content_text = article.content_text or article.summary
