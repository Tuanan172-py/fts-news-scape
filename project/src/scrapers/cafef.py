"""Bộ thu thập dữ liệu nguồn CafeF (kết hợp API nội bộ và RSS theo chuyên mục)."""

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
    """Phân tích chuỗi ngày timestamp của CafeF sang mốc thời gian ISO 8601.

    Args:
        raw: Chuỗi ngày thô có dạng '/Date(...)/'.

    Returns:
        Chuỗi thời gian chuẩn ISO 8601 hoặc None nếu không khớp định dạng.
    """
    m = _DATE_RE.search(raw or "")
    if not m:
        return None
    dt = datetime.fromtimestamp(int(m.group(1)) / 1000, tz=VN_TZ)
    return dt.isoformat(timespec="seconds")


@register("cafef")
class CafeFScraper(CaptureMixin, BaseScraper):
    """Lớp thu thập tin tức từ CafeF qua API theo mã cổ phiếu và RSS chuyên mục.

    Attributes:
        endpoint: Địa chỉ API Ajax lấy danh sách bài viết.
        params: Tham số truy vấn API.
        headers: Các HTTP header yêu cầu cho API.
        content_selector: Bộ chọn CSS vùng nội dung bài viết.
        max_details: Số lượng bài chi tiết tối đa cần lấy mỗi chu kỳ.
        watchlist: Danh sách mã cổ phiếu theo dõi.
        feeds: Danh sách RSS feed chuyên mục bổ sung.
    """
    BASE_URL = "https://cafef.vn"

    def __init__(self, config, http, dedup):
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
        """Lấy danh sách các bài viết thô từ API mã cổ phiếu và RSS chuyên mục.

        Returns:
            Danh sách các dictionary chứa dữ liệu thô của bài viết.
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
        # Nhánh RSS per-category — bổ sung tin không gắn mã CK.
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
        """Phân tích bản ghi thô từ API hoặc RSS thành đối tượng Article.

        Args:
            raw: Bản ghi thô từ phản hồi API hoặc RSS feed.

        Returns:
            Đối tượng Article hoặc None nếu bản ghi không hợp lệ.
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
        """Phân tích một bản ghi RSS feed chuyên mục thành đối tượng Article.

        Args:
            raw: Bản ghi dữ liệu RSS entry.

        Returns:
            Đối tượng Article hoặc None nếu thiếu thông tin URL/tiêu đề.
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
        """Tải trang chi tiết và lưu trữ Bronze byte-exact cho bài viết.

        Args:
            article: Đối tượng Article cần bổ sung nội dung chi tiết.
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
