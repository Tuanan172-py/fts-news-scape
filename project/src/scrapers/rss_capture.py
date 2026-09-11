"""Bộ thu thập dữ liệu RSS tích hợp lưu trữ Bronze byte-exact cho trang chi tiết."""

from __future__ import annotations

from bs4 import BeautifulSoup
from loguru import logger

from src.core.models import Article
from src.processor.extractor import extract_text
from src.scrapers import register
from src.scrapers.capture_mixin import CaptureMixin
from src.scrapers.rss_generic import RSSScraper


def _meta_content(html: str, key: str) -> str:
    """Trích xuất giá trị thuộc tính content từ thẻ meta trong tài liệu HTML.

    Args:
        html: Chuỗi mã nguồn HTML trang chi tiết.
        key: Tên thuộc tính (name hoặc property) của thẻ meta.

    Returns:
        Nội dung thuộc tính content hoặc chuỗi rỗng nếu không tìm thấy.
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
    """Lớp thu thập RSS kết hợp lưu trữ nguyên bản Bronze và phân tích DOM bài viết.

    Attributes:
        content_selector: Bộ chọn CSS xác định vùng nội dung chính.
        category_meta: Tên thẻ meta trích xuất chuyên mục bổ sung nếu có.
        base_url: Đường dẫn gốc của nguồn tin.
    """

    def __init__(self, config, http, dedup):
        super().__init__(config, http, dedup)
        detail = config.get("detail", {})
        self.content_selector = detail.get("content_selector") or "article"
        self.category_meta = detail.get("category_meta", "")
        self.base_url = config.get("base_url", "")
        self._init_capture()

    def enrich(self, article: Article) -> None:
        """Thu thập trang chi tiết, lưu trữ tạo tác Bronze và bóc tách nội dung bài viết.

        Args:
            article: Đối tượng Article cần bổ sung dữ liệu.
        """
        # inline = content:encoded (nếu feed có). Pop để không ghi vào metadata_json.
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
            # capture fail/skip — mixin đã set content_text=summary + ghi self.errors.
            # content:encoded chỉ là body DỰ PHÒNG, KHÔNG phải Bronze.
            if inline:
                article.content_html = inline
                article.content_text = extract_text(inline) or article.summary
            return

        self._details_fetched += 1
        article.content_text = extract_text(article.content_html) or article.summary
        if self.category_meta:
            section = _meta_content(html, self.category_meta)
            if section and section not in article.categories:
                article.categories.insert(0, section)  # chuyên mục thật đứng đầu
