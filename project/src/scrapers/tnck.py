"""
TNCK (Tin nhanh chứng khoán / ĐTCK) scraper — zone-based JSON API.

Endpoint: GET https://api.tinnhanhchungkhoan.vn/api/morenews-zone-{zone}-{page}.html
Verified 2026-07-24:
- Response gzip (requests tự decompress), data.contents[] 40 items/page
- `phrase` param BỊ IGNORE (server trả zone content y hệt) → không dùng;
  ticker tagging client-side qua core/tickers.py
- Field `date` = epoch seconds (string); `url` relative
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from loguru import logger

from src.core.base_scraper import BaseScraper
from src.core.config import load_watchlist
from src.core.models import Article
from src.core.tickers import tag_tickers
from src.processor.extractor import extract_content
from src.scrapers import register

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


@register("tnck")
class TnckScraper(BaseScraper):
    BASE_URL = "https://www.tinnhanhchungkhoan.vn"
    API_TEMPLATE = "https://api.tinnhanhchungkhoan.vn/api/morenews-zone-{zone}-{page}.html"

    def __init__(self, config, http, dedup):
        super().__init__(config, http, dedup)
        api = config.get("api", {})
        self.template = api.get("url_template", self.API_TEMPLATE)
        self.zones = api.get("zones", [4])
        self.pages_per_cycle = api.get("pages_per_cycle", 2)
        self.headers = api.get("headers", {"Referer": f"{self.BASE_URL}/"})
        detail = config.get("detail", {})
        self.max_details = detail.get("max_details_per_cycle", 30)
        self.watchlist = config.get("watchlist") or load_watchlist()
        self._details_fetched = 0

    def fetch_list(self) -> list[dict]:
        self._details_fetched = 0
        items: list[dict] = []
        for zone in self.zones:
            for page in range(1, self.pages_per_cycle + 1):
                url = self.template.format(zone=zone, page=page)
                data = self.http.get_json(url, referer=f"{self.BASE_URL}/",
                                          headers=self.headers,
                                          timeout=self.config.get("timeout", 30))
                if not data:
                    self.errors.append(f"zone {zone} page {page} fetch failed")
                    continue
                contents = (data.get("data") or {}).get("contents") or []
                if not contents:
                    logger.info("[tnck] zone {} page {} empty", zone, page)
                items.extend(contents)
        return items

    def parse_item(self, raw: dict) -> Article | None:
        title = (raw.get("title") or "").strip()
        rel_url = (raw.get("url") or "").strip()
        if not title or not rel_url:
            logger.warning("[tnck] item missing title/url, skipped")
            return None

        published = ""
        raw_date = raw.get("date")
        if raw_date:
            try:
                dt = datetime.fromtimestamp(int(raw_date), tz=VN_TZ)
                published = dt.isoformat(timespec="seconds")
            except (ValueError, OSError):
                logger.warning("[tnck] bad epoch date: {!r}", raw_date)

        summary = (raw.get("description") or "").strip()
        zone_name = (raw.get("zone") or {}).get("name", "")
        return Article(
            url=urljoin(self.BASE_URL, rel_url),
            title=title,
            source_domain="tinnhanhchungkhoan.vn",
            summary=summary,
            published_at=published,
            symbols=tag_tickers(f"{title} {summary}", self.watchlist),
            categories=[zone_name] if zone_name else [],
            metadata={"content_id": raw.get("content_id", ""),
                      "avatar_url": raw.get("avatar_url", "")},
        )

    def enrich(self, article: Article) -> None:
        if self._details_fetched >= self.max_details:
            article.content_text = article.summary
            article.metadata["detail_deferred"] = True
            return
        html = self.http.get(article.url, referer=f"{self.BASE_URL}/",
                             timeout=self.config.get("timeout", 30))
        if html is None:
            article.content_text = article.summary
            self.errors.append(f"detail fetch failed: {article.url}")
            return
        self._details_fetched += 1
        result = extract_content(article.url, html=html)
        article.content_html = result["raw_html"]
        article.content_text = result["content"] or article.summary
