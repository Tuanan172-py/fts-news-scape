"""
RssCaptureScraper — RSS list + Bronze full-capture detail (method: rss_capture).

Kế thừa RSSScraper: fetch_list/parse_item/filter.any|none/link_rewrites dùng lại
NGUYÊN VẸN (DRY — không copy-paste). Chỉ override enrich() để lưu raw HTML
byte-exact qua RawStore TRƯỚC mọi parse (design 06 §2, bất biến AC7).
Nguồn RSS mới cần Bronze = 1 file YAML, 0 code.

Registry key '_rss_capture' → build_scraper() map qua `method: rss_capture`
(orchestrator.py: REGISTRY.get(name) or REGISTRY.get(f"_{method}")).

Khác RSSScraper ở đúng 1 điểm hành vi: content:encoded KHÔNG còn được dùng để
BỎ QUA fetch detail — inline HTML không phải Bronze. Nó chỉ là body dự phòng khi
capture thất bại.

⚠ content_selector là BẮT BUỘC trong config: selector miss → _looks_complete=False
→ capture_status=partial + missing[incomplete_render] → change_detect.classify()
= SELECTOR_BROKEN → agent HOLD bài. _density_extract chỉ vá content_html, KHÔNG
vá capture_status.
"""

from __future__ import annotations

from bs4 import BeautifulSoup
from loguru import logger

from src.core.models import Article
from src.processor.extractor import extract_text
from src.scrapers import register
from src.scrapers.capture_mixin import CaptureMixin
from src.scrapers.rss_generic import RSSScraper


def _meta_content(html: str, key: str) -> str:
    """Đọc <meta property|name="{key}" content="..."> từ trang detail.

    Dùng cho nguồn có feed gộp chung (không phân chuyên mục) nhưng trang detail
    khai chuyên mục thật, vd TBTC: <meta property="article:section" content="...">.
    Trả "" khi không có — KHÔNG raise.
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
    """MRO: RssCaptureScraper → CaptureMixin → RSSScraper → BaseScraper.

    CaptureMixin không định nghĩa __init__ nên super().__init__ rơi đúng vào
    RSSScraper.__init__ (nhận feeds/max_details/watchlist/language/filter/...).
    """

    def __init__(self, config, http, dedup):
        super().__init__(config, http, dedup)
        detail = config.get("detail", {})
        self.content_selector = detail.get("content_selector") or "article"
        # Tuỳ chọn: lấy chuyên mục THẬT từ meta tag của trang detail. Cần khi feed
        # gộp chung mọi chuyên mục (vd TBTC) — khi đó tên feed KHÔNG phải chuyên mục.
        self.category_meta = detail.get("category_meta", "")
        self.base_url = config.get("base_url", "")
        self._init_capture()  # RawStore + RobotsGate + SourceBackoff

    def enrich(self, article: Article) -> None:
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
