"""Scrape Bao Dau Tu (baodautu.vn) article lists from HTML category pages and capture full article details with Bronze raw capture."""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from src.core.base_scraper import BaseScraper
from src.core.config import load_watchlist
from src.core.htmltitle import extract_page_title, is_valid_title
from src.core.models import VN_TZ, Article
from src.core.pagination import paginate_until_known
from src.core.urlnorm import url_key
from src.core.tickers import tag_tickers
from src.processor.extractor import extract_text
from src.scrapers import register
from src.scrapers.capture_mixin import CaptureMixin

BASE_URL = "https://baodautu.vn"
SOURCE_DOMAIN = "baodautu.vn"
_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})\b")


def _parse_detail_date(html: str, scope_selector: str) -> str:
    """Extract the publication date in dd/MM/yyyy HH:mm format and convert it to ISO 8601.

    Args:
        html: HTML source of the article detail page.
        scope_selector: CSS selector of the element that holds the publication date string.

    Returns:
        ISO 8601 date string with the +07:00 offset, or an empty string when not found.
    """
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "lxml")
        node = soup.select_one(scope_selector) or soup
        m = _DATE_RE.search(node.get_text(" ", strip=True))
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[baodautu] date parse failed: {}", e)
        return ""
    if not m:
        return ""
    d, mo, y, hh, mm = (int(g) for g in m.groups())
    try:
        return datetime(y, mo, d, hh, mm, tzinfo=VN_TZ).isoformat(timespec="seconds")
    except ValueError:
        return ""


def _slug_title(href: str) -> str:
    """Build a provisional title from the URL slug when the listing has no valid title.

    Args:
        href: Article path such as `/ten-bai-d123456.html`.

    Returns:
        Words of the slug with the `-d<number>` article id removed.
    """
    slug = href.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"-d\d+\.html.*$", "", slug)
    return slug.replace("-", " ").strip()


@register("baodautu")
class BaodautuScraper(CaptureMixin, BaseScraper):
    """Scrape Bao Dau Tu by extracting articles from HTML category pages.

    Attributes:
        categories: Category configs to scrape.
        pages_per_cycle: Number of category pages to visit per cycle.
        max_pages: Maximum number of pages per category.
        item_selector: CSS selector of the article block.
        link_selector: CSS selector of the article link.
        sapo_selector: CSS selector of the short summary (sapo).
        link_pattern: Regular expression that validates article link format.
        content_selector: CSS selector of the article detail content area.
        date_scope: CSS selector that locates the publication time.
        author_selector: CSS selector of the author.
        max_details: Maximum number of article details to fetch per cycle.
        base_url: Root URL of the news site.
        watchlist: Stock tickers to watch and tag.
        language: Language code of the article content.
    """

    def __init__(self, config, http, dedup):
        """Initialize the scraper from its source config.

        Args:
            config: Source config dict.
            http: HTTP client.
            dedup: Deduplication cache.
        """
        super().__init__(config, http, dedup)
        listing = config.get("listing", {}) or {}
        self.categories = listing.get("categories", [])
        self.pages_per_cycle = listing.get("pages_per_cycle", 1)
        self.max_pages = listing.get("max_pages", 8)
        self.item_selector = listing.get("item_selector", "article")
        self.link_selector = listing.get("link_selector", "a[href]")
        self.sapo_selector = listing.get(
            "sapo_selector", "div.sapo_thumb_news, div.desc_list_news_home")
        self.link_pattern = re.compile(
            listing.get("link_pattern", r"-d\d+\.html"))
        detail = config.get("detail", {}) or {}
        self.content_selector = detail.get("content_selector", "#content_detail_news")
        self.date_scope = detail.get("date_scope_selector", "span.post-time")
        self.author_selector = detail.get("author_selector", "a.author")
        self.max_details = detail.get("max_details_per_cycle", 30)
        self.base_url = (config.get("base_url") or BASE_URL).rstrip("/")
        self.watchlist = config.get("watchlist") or load_watchlist()
        self.language = config.get("language", "vi")
        self._details_fetched = 0
        self._init_capture()

    # -- listing ------------------------------------------------------------
    def _page_url(self, slug: str, cid, page: int) -> str:
        """Build the paginated URL of a category."""
        return (f"{self.base_url}/{slug}-d{cid}/" if page == 1
                else f"{self.base_url}/{slug}-d{cid}/p{page}")

    def _parse_listing(self, html: str, cat: dict, listing_url: str) -> list[dict]:
        """Parse category HTML to extract the article list.

        Args:
            html: HTML string of the category page.
            cat: Config of the current category.
            listing_url: URL of the category page being processed.

        Returns:
            One dict per extracted raw article.
        """
        out: list[dict] = []
        try:
            blocks = BeautifulSoup(html, "lxml").select(self.item_selector)
        except Exception as e:  # pragma: no cover - defensive
            self.errors.append(f"listing parse error {listing_url}: {e}")
            return out
        for b in blocks:
            href = title = ""
            for a in b.select(self.link_selector):
                cand_href = (a.get("href") or "").strip()
                if not cand_href or not self.link_pattern.search(cand_href):
                    continue
                img = a.find("img")
                cand_title = max(
                    (a.get_text(" ", strip=True), a.get("title") or "",
                     (img.get("alt") or "") if img else ""), key=len).strip()
                if len(cand_title) > len(title) or not href:
                    href, title = cand_href, cand_title
            if not href:
                continue
            from_slug = not is_valid_title(title)
            if from_slug:
                title = _slug_title(href)
            if not title:
                continue
            sapo_node = b.select_one(self.sapo_selector)
            out.append({
                "link": href,
                "title": title,
                "_title_from_slug": from_slug,
                "sapo": sapo_node.get_text(" ", strip=True) if sapo_node else "",
                "_cat_name": cat.get("name", ""),
                "_listing_url": listing_url,
            })
        return out

    def fetch_list(self) -> list[dict]:
        """Collect raw article entries from the configured category pages.

        Returns:
            Raw articles obtained through HTTP GET.
        """
        self._details_fetched = 0
        items: list[dict] = []
        for cat in self.categories:
            def fetch_page(page: int, cat=cat) -> list[dict] | None:
                url = self._page_url(cat["slug"], cat["id"], page)
                html = self.http.get(url, referer=f"{self.base_url}/",
                                     timeout=self.config.get("timeout", 30))
                if html is None:
                    self.errors.append(f"listing fetch failed: {url}")
                    return None
                found = self._parse_listing(html, cat, url)
                if not found and page == 1:
                    self.errors.append(f"listing 0 items (template drift?): {url}")
                return found

            items.extend(paginate_until_known(
                fetch_page,
                lambda it: url_key(urljoin(self.base_url + "/", it["link"])),
                self.dedup.known_keys,
                min_pages=self.pages_per_cycle, max_pages=self.max_pages,
                errors=self.errors, label=f"baodautu/{cat.get('name', cat.get('slug'))}"))
        return items

    def parse_item(self, raw: dict) -> Article | None:
        """Convert a raw category entry into an Article.

        Args:
            raw: Raw article data collected from the category page.

        Returns:
            Valid Article, or None when the URL or title is missing.
        """
        url = (raw.get("link") or "").strip()
        title = (raw.get("title") or "").strip()
        if not url or not title:
            return None
        summary = (raw.get("sapo") or "").strip()
        cat = raw.get("_cat_name") or ""
        return Article(
            url=urljoin(self.base_url + "/", url),
            title=title,
            source_domain=SOURCE_DOMAIN,
            summary=summary,
            published_at="",
            symbols=tag_tickers(f"{title} {summary}", self.watchlist),
            categories=[cat] if cat else [],
            metadata={"language": self.language,
                      "listing_url": raw.get("_listing_url", ""),
                      **({"title_from_slug": True} if raw.get("_title_from_slug") else {})},
        )

    # -- detail -------------------------------------------------------------
    def enrich(self, article: Article) -> None:
        """Add detail content, author and publication date, and store the Bronze capture.

        Args:
            article: Article to enrich.
        """
        if self._details_fetched >= self.max_details:
            article.content_text = article.summary
            article.metadata["detail_deferred"] = True
            return
        html = self._capture_and_extract(article, SOURCE_DOMAIN,
                                         f"{self.base_url}/", self.content_selector)
        if html is None:
            return
        self._details_fetched += 1
        if article.metadata.pop("title_from_slug", False):
            article.title = extract_page_title(html) or article.title

        article.published_at = _parse_detail_date(html, self.date_scope)
        if not article.published_at:
            article.metadata.setdefault("capture", {}) \
                .setdefault("missing", []).append("published_at")

        if self.author_selector:
            try:
                node = BeautifulSoup(html, "lxml").select_one(self.author_selector)
                if node is not None:
                    article.author = node.get_text(" ", strip=True)
            except Exception as e:  # pragma: no cover - defensive
                logger.debug("[baodautu] author parse failed: {}", e)

        article.content_text = extract_text(article.content_html) or article.summary
