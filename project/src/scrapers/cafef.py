"""
CafeF scraper — internal JSON API, symbol-driven theo watchlist.

Endpoint: GET https://cafef.vn/du-lieu/Ajax/PageNew/News.ashx
Params bắt buộc: symbol (lowercase), Type=1 (verified 2026-07-24 — Type=2 trả rỗng).
Date format: /Date(ms_epoch[+tz])/ — parse riêng.
Detail: div#mainContent giữ raw HTML, trafilatura cho text sạch.
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from loguru import logger

from src.core.base_scraper import BaseScraper
from src.core.config import load_watchlist
from src.core.models import Article
from src.processor.extractor import extract_text
from src.scrapers import register

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
_DATE_RE = re.compile(r"/Date\((\d+)(?:[+-]\d{4})?\)/")


def parse_cafef_date(raw: str) -> str | None:
    """'/Date(1784543714000)/' hoặc '/Date(...+0700)/' → ISO 8601 giờ VN."""
    m = _DATE_RE.search(raw or "")
    if not m:
        return None
    dt = datetime.fromtimestamp(int(m.group(1)) / 1000, tz=VN_TZ)
    return dt.isoformat(timespec="seconds")


@register("cafef")
class CafeFScraper(BaseScraper):
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
        self._details_fetched = 0

    def fetch_list(self) -> list[dict]:
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
        return items

    def parse_item(self, raw: dict) -> Article | None:
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

    def enrich(self, article: Article) -> None:
        if self._details_fetched >= self.max_details:
            # quá cap → giữ summary, không fetch (incremental delivery)
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

        node = BeautifulSoup(html, "lxml").select_one(self.content_selector)
        if node is not None:
            article.content_html = str(node)
        else:
            logger.warning("[cafef] selector '{}' miss on {} — dùng full page",
                           self.content_selector, article.url)
            article.content_html = html
        article.content_text = extract_text(article.content_html) or article.summary
