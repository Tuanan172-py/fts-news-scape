"""Bộ thu thập dữ liệu báo Tin nhanh chứng khoán (tinnhanhchungkhoan.vn).

Cung cấp lớp TnckScraper thu thập danh sách bài viết từ JSON API và tải chi tiết
kèm capture tầng Bronze.
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
    """Bộ thu thập dữ liệu báo Tin nhanh chứng khoán qua API zone.

    Attributes:
        BASE_URL: Địa chỉ web cơ sở của trang tin.
        SOURCE_DOMAIN: Tên miền nguồn chuẩn hóa không chứa www.
        API_TEMPLATE: Mẫu URL gọi API lấy danh sách bài theo zone.
        template: Mẫu định dạng URL API sau cấu hình.
        zones: Danh sách mã chuyên mục zone cần thu thập.
        pages_per_cycle: Số trang cần quét trong mỗi chu kỳ.
        headers: Các tiêu đề HTTP kèm theo yêu cầu API.
        content_selector: Bộ chọn CSS vùng nội dung chi tiết bài viết.
        max_details: Số bài viết chi tiết tối đa cần lấy trong một chu kỳ.
        watchlist: Danh mục mã cổ phiếu cần theo dõi và gán nhãn.
        language: Mã ngôn ngữ nội dung bài viết.
    """

    BASE_URL = "https://www.tinnhanhchungkhoan.vn"
    SOURCE_DOMAIN = "tinnhanhchungkhoan.vn"
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
        self._init_capture()

    def fetch_list(self) -> list[dict]:
        """Thu thập danh sách bài viết từ JSON API theo các zone cấu hình.

        Returns:
            Danh sách bài viết thô trích xuất từ dữ liệu JSON.
        """
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
        """Chuyển đổi từ điển dữ liệu bài viết thô sang đối tượng Article.

        Args:
            raw: Dữ liệu bài viết thô từ API.

        Returns:
            Đối tượng Article hợp lệ, hoặc None nếu thiếu trường bắt buộc.
        """
        title = (raw.get("title") or "").strip()
        rel_url = (raw.get("url") or "").strip()
        if not title or not rel_url:
            logger.warning("[tnck] item missing title/url, skipped")
            return None

        published = ""
        raw_date = raw.get("date")
        if raw_date:
            try:
                published = datetime.fromtimestamp(int(raw_date), tz=VN_TZ) \
                    .isoformat(timespec="seconds")
            except (ValueError, OSError, TypeError):
                logger.warning("[tnck] bad epoch date: {!r}", raw_date)

        summary = (raw.get("description") or "").strip()
        zone = raw.get("zone") or {}
        zone_name = zone.get("name") or ""
        return Article(
            url=urljoin(self.BASE_URL, rel_url),
            title=title,
            source_domain=self.SOURCE_DOMAIN,
            summary=summary,
            published_at=published,
            symbols=tag_tickers(f"{title} {summary}", self.watchlist),
            categories=[zone_name] if zone_name else [],
            metadata={"content_id": raw.get("content_id", ""),
                      "avatar_url": raw.get("avatar_url", ""),
                      "zone_id": zone.get("zone_id", ""),
                      "language": self.language},
        )

    def enrich(self, article: Article) -> None:
        """Bổ sung nội dung bài viết chi tiết và lưu trữ capture tầng Bronze.

        Args:
            article: Đối tượng Article cần bổ sung nội dung.
        """
        if self._details_fetched >= self.max_details:
            article.content_text = article.summary
            article.metadata["detail_deferred"] = True
            return
        html = self._capture_and_extract(article, self.SOURCE_DOMAIN,
                                         f"{self.BASE_URL}/", self.content_selector)
        if html is None:
            return
        self._details_fetched += 1
        article.content_text = extract_text(article.content_html) or article.summary
