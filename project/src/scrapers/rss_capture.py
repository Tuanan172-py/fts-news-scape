"""Scrape RSS feeds and store byte-exact Bronze copies of the detail pages."""

from __future__ import annotations

from bs4 import BeautifulSoup
from loguru import logger

from src.core.models import Article
from src.processor.extractor import extract_text
from src.scrapers import register
from src.scrapers.capture_mixin import CaptureMixin
from src.scrapers.rss_generic import RSSScraper


def _meta_content(html: str, key: str) -> str:
    """Extract the content attribute value of a meta tag in an HTML document.

    Args:
        html: HTML source of the detail page.
        key: Attribute value (name or property) that identifies the meta tag.

    Returns:
        Value of the content attribute, or an empty string when not found.
    """
    if not html or not key:
        return ""
    try:
        soup = BeautifulSoup(html, "lxml")
        tag = (soup.find("meta", attrs={"property": key})
               or soup.find("meta", attrs={"name": key}))
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("meta parse failed for {}: {}", key, e)
        return ""
    return (tag.get("content") or "").strip() if tag else ""


@register("_rss_capture")
class RssCaptureScraper(CaptureMixin, RSSScraper):
    """Scrape RSS feeds with verbatim Bronze storage and article DOM parsing.

    Attributes:
        content_selector: CSS selector of the main content area.
        category_meta: Name of the meta tag that provides an extra category, if any.
        base_url: Root URL of the news source.
    """

    def __init__(self, config, http, dedup):
        """Initialize the scraper from its source config.

        Args:
            config: Source config dict.
            http: HTTP client.
            dedup: Deduplication cache.
        """
        super().__init__(config, http, dedup)
        detail = config.get("detail", {})
        self.content_selector = detail.get("content_selector") or "article"
        self.category_meta = detail.get("category_meta", "")
        self.base_url = config.get("base_url", "")
        self._init_capture()

    def enrich(self, article: Article) -> None:
        """Capture the detail page, store the Bronze artifact and extract the article content.

        Args:
            article: Article to enrich.
        """
        # inline = content:encoded (when the feed has it). Popped so it is not written to metadata_json.
        inline = article.metadata.pop("_inline_html", "")

        if self._details_fetched >= self.max_details:
            article.content_text = extract_text(inline) if inline else article.summary
            article.content_text = article.content_text or article.summary
            article.metadata["detail_deferred"] = True
            return

        referer = self.base_url or f"https://{article.source_domain}/"
        html = self._capture_and_extract(article, article.source_domain,
                                         referer, self.content_selector)
        if html is None:
            # Capture failed or skipped: the mixin already set content_text=summary and recorded self.errors.
            # content:encoded is only a fallback body, not Bronze.
            if inline:
                article.content_html = inline
                article.content_text = extract_text(inline) or article.summary
            return

        self._details_fetched += 1
        article.content_text = extract_text(article.content_html) or article.summary
        if self.category_meta:
            section = _meta_content(html, self.category_meta)
            if section and section not in article.categories:
                article.categories.insert(0, section)  # the real section goes first
