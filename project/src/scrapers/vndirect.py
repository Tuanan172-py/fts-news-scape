"""Bộ thu thập dữ liệu tin tức từ VNDirect (vndirect.com.vn).

Cung cấp lớp VndirectScraper trích xuất bài viết thông qua JSON API công khai
của hệ thống VNDirect.
"""

from __future__ import annotations

from loguru import logger

from src.core.base_scraper import BaseScraper
from src.core.models import Article
from src.processor.extractor import extract_text
from src.scrapers import register


@register("vndirect")
class VndirectScraper(BaseScraper):
    """Bộ thu thập tin tức qua giao diện lập trình ứng dụng REST của VNDirect.

    Attributes:
        API_URL: Địa chỉ mặc định của API tin tức VNDirect.
        api_url: Địa chỉ endpoint API sau cấu hình.
        page_size: Số lượng bản ghi tin tức lấy trong một trang.
        news_groups: Danh sách nhóm tin tức cần lọc.
        max_details: Giới hạn số bài viết cần tải nội dung mở rộng nếu thiếu.
    """

    API_URL = "https://api-finfo.vndirect.com.vn/v4/news"

    def __init__(self, config, http, dedup):
        super().__init__(config, http, dedup)
        api = config.get("api", {})
        self.api_url = api.get("endpoint", self.API_URL)
        self.page_size = api.get("page_size", 60)
        self.news_groups = api.get("news_groups", [])
        self.max_details = config.get("detail", {}).get("max_details_per_cycle", 20)
        self._details_fetched = 0

    def fetch_list(self) -> list[dict]:
        """Thu thập danh sách tin tức từ REST API của VNDirect.

        Returns:
            Danh sách đối tượng từ điển chứa dữ liệu tin tức thô.
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
        """Chuyển đổi bản ghi tin tức từ API VNDirect thành đối tượng Article.

        Args:
            raw: Từ điển bản ghi tin tức thô từ API.

        Returns:
            Đối tượng Article hợp lệ, hoặc None nếu thiếu tiêu đề hoặc liên kết.
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
        """Bổ sung nội dung văn bản chi tiết cho bài viết.

        Nếu nội dung chưa có trong phản hồi danh sách, tải bổ sung từ URL gốc.

        Args:
            article: Đối tượng Article cần bổ sung nội dung.
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
