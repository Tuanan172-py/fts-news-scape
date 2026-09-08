"""
TNCK (Tin nhanh chứng khoán / ĐTCK) scraper — zone JSON API + Bronze full capture.

Endpoint: GET https://api.tinnhanhchungkhoan.vn/api/morenews-zone-{zone}-{page}.html

KHÔNG CÓ RSS (verified 2026-09-07): /rss.html trả 13 bytes rỗng; /rss/*.rss và
/chung-khoan.rss đều 302 + 0 byte. API zone là route DUY NHẤT — đừng probe lại.

Verified 2026-09-07:
- Response gzip (requests tự decompress), `data.contents[]` 40 items/page.
- `date` = epoch GIÂY, JSON **NUMBER** (docs cũ ghi "string" — SAI). int() nhận cả hai.
- `url` relative → urljoin về host www.
- `phrase` param BỊ SERVER IGNORE → không filter ticker được; tag client-side.
- `zone` object echo sẵn {zone_id, parent_id, name, url} → categories tự mô tả.
- robots www: Disallow /api/ /search/ /tag.html /print.html ... nhưng
  **api.tinnhanhchungkhoan.vn là HOST KHÁC** (robots riêng, rỗng). Trang chi tiết
  /<slug>-post<NNN>.html được PHÉP. Không khai Crawl-delay → giữ mặc định 3.0s.
- Detail server-rendered, body = div.article__body.cms-body.
  Quảng cáo nằm trong div[id^=adsWeb_] BÊN TRONG body — strip ở Silver, KHÔNG đụng Bronze.

source_domain chuẩn hoá **NON-WWW** = "tinnhanhchungkhoan.vn" (khớp quy ước
removeprefix("www.") toàn repo). `article.url` GIỮ host www của API — đổi URL sẽ đổi
url_title_hash tức đổi định danh bài.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urljoin

from loguru import logger

from src.core.base_scraper import BaseScraper
from src.core.config import load_watchlist
from src.core.models import VN_TZ, Article
from src.core.tickers import tag_tickers
from src.processor.extractor import extract_text
from src.scrapers import register
from src.scrapers.capture_mixin import CaptureMixin


@register("tnck")
class TnckScraper(CaptureMixin, BaseScraper):
    BASE_URL = "https://www.tinnhanhchungkhoan.vn"
    SOURCE_DOMAIN = "tinnhanhchungkhoan.vn"   # non-www — QUYẾT ĐỊNH, xem docstring
    API_TEMPLATE = "https://api.tinnhanhchungkhoan.vn/api/morenews-zone-{zone}-{page}.html"

    def __init__(self, config, http, dedup):
        super().__init__(config, http, dedup)
        api = config.get("api", {})
        self.template = api.get("url_template", self.API_TEMPLATE)
        self.zones = api.get("zones", [4])
        self.pages_per_cycle = api.get("pages_per_cycle", 1)
        self.headers = api.get("headers", {"Referer": f"{self.BASE_URL}/"})
        detail = config.get("detail", {})
        self.content_selector = detail.get("content_selector", "div.article__body")
        self.max_details = detail.get("max_details_per_cycle", 40)
        self.watchlist = config.get("watchlist") or load_watchlist()
        self.language = config.get("language", "vi")
        self._details_fetched = 0
        self._init_capture()   # RawStore + RobotsGate + SourceBackoff

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
                    continue          # zone-level isolation, KHÔNG raise
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
                # epoch giây — API trả NUMBER, int() nhận cả str lẫn int
                published = datetime.fromtimestamp(int(raw_date), tz=VN_TZ) \
                    .isoformat(timespec="seconds")
            except (ValueError, OSError, TypeError):
                logger.warning("[tnck] bad epoch date: {!r}", raw_date)

        summary = (raw.get("description") or "").strip()
        zone = raw.get("zone") or {}
        zone_name = zone.get("name") or ""
        return Article(
            url=urljoin(self.BASE_URL, rel_url),      # giữ host www của API
            title=title,
            source_domain=self.SOURCE_DOMAIN,          # non-www
            summary=summary,
            published_at=published,
            symbols=tag_tickers(f"{title} {summary}", self.watchlist),
            categories=[zone_name] if zone_name else [],
            metadata={"content_id": raw.get("content_id", ""),
                      "avatar_url": raw.get("avatar_url", ""),
                      "zone_id": zone.get("zone_id", ""),
                      "language": self.language},      # BẮT BUỘC (thiếu ở bản cũ)
        )

    def enrich(self, article: Article) -> None:
        if self._details_fetched >= self.max_details:
            article.content_text = article.summary
            article.metadata["detail_deferred"] = True
            return
        html = self._capture_and_extract(article, self.SOURCE_DOMAIN,
                                         f"{self.BASE_URL}/", self.content_selector)
        if html is None:
            return    # mixin đã set content_text=summary + ghi self.errors
        self._details_fetched += 1
        article.content_text = extract_text(article.content_html) or article.summary
