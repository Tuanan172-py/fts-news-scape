"""Bộ thu thập dữ liệu báo Vietstock (vietstock.vn).

Cung cấp lớp VietstockScraper thu thập danh sách bài viết từ các kênh RSS và tải
chi tiết nội dung HTML kèm lưu trữ tầng Bronze.
"""

from __future__ import annotations

from urllib.parse import urlparse

import feedparser
from loguru import logger

from src.core.base_scraper import BaseScraper
from src.core.config import load_watchlist
from src.core.models import Article
from src.core.tickers import tag_tickers
from src.processor.extractor import extract_text
from src.scrapers import register
from src.scrapers.capture_mixin import CaptureMixin
from src.scrapers.rss_generic import (
    _clean_title,
    _decode_feed,
    _parse_entry_date,
)

BASE_URL = "https://vietstock.vn"


@register("vietstock")
class VietstockScraper(CaptureMixin, BaseScraper):
    """Bộ thu thập dữ liệu báo Vietstock kết hợp nguồn cấp RSS và tải chi tiết HTML.

    Attributes:
        feeds: Danh sách cấu hình các kênh RSS cần đọc.
        content_selector: Bộ chọn CSS vùng nội dung chi tiết bài viết.
        max_details: Số bài viết chi tiết tối đa cần tải trong mỗi chu kỳ.
        watchlist: Danh mục mã cổ phiếu cần theo dõi và gán nhãn.
        language: Mã ngôn ngữ nội dung bài viết.
    """

    def __init__(self, config, http, dedup):
        super().__init__(config, http, dedup)
        self.feeds = config.get("rss", {}).get("feeds", [])
        detail = config.get("detail", {})
        self.content_selector = detail.get(
            "content_selector", "div.article-content, div.single_post_content, article")
        self.max_details = detail.get("max_details_per_cycle", 30)
        self.watchlist = config.get("watchlist") or load_watchlist()
        self.language = config.get("language", "vi")
        self._details_fetched = 0
        self._init_capture()

    def fetch_list(self) -> list[dict]:
        """Thu thập danh sách bài viết từ các kênh cấp tin RSS của Vietstock.

        Returns:
            Danh sách bài viết thô trích xuất từ các kênh RSS.
        """
        self._details_fetched = 0
        items: list[dict] = []
        for feed_cfg in self.feeds:
            feed_url = feed_cfg["url"]
            feed_name = feed_cfg.get("name", feed_url)
            raw = self.http.get_bytes(feed_url, timeout=self.config.get("timeout", 30))
            if raw is None:
                self.errors.append(f"feed fetch failed: {feed_name}")
                continue
            feed = feedparser.parse(_decode_feed(raw))
            if feed.bozo and not feed.entries:
                self.errors.append(f"feed parse failed: {feed_name}")
                continue
            for e in feed.entries:
                items.append({
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
        """Chuyển đổi dữ liệu bài viết từ mục cấp tin RSS sang đối tượng Article.

        Args:
            raw: Dữ liệu bài viết thô từ RSS.

        Returns:
            Đối tượng Article hợp lệ, hoặc None nếu thiếu URL hoặc tiêu đề.
        """
        url = raw["link"]
        title = _clean_title(raw["title"])
        if not url or not title:
            return None
        summary_text = extract_text(raw["summary"]) if "<" in raw["summary"] \
            else raw["summary"]
        return Article(
            url=url,
            title=title,
            source_domain=urlparse(url).netloc.removeprefix("www."),
            summary=summary_text,
            published_at=_parse_entry_date(raw),
            author=raw["author"],
            symbols=tag_tickers(f"{title} {summary_text}", self.watchlist),
            categories=[raw["_feed_name"]],
            metadata={"feed_name": raw["_feed_name"], "language": self.language},
        )

    def enrich(self, article: Article) -> None:
        """Bổ sung nội dung chi tiết bài viết qua HTML và lưu trữ capture tầng Bronze.

        Args:
            article: Đối tượng Article cần bổ sung chi tiết nội dung.
        """
        if self._details_fetched >= self.max_details:
            article.content_text = article.summary
            article.metadata["detail_deferred"] = True
            return
        html = self._capture_and_extract(article, "vietstock.vn",
                                         f"{BASE_URL}/", self.content_selector)
        if html is None:
            return
        self._details_fetched += 1
        article.content_text = extract_text(article.content_html) or article.summary
