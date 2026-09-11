"""Bộ thu thập dữ liệu báo Báo Đầu Tư (baodautu.vn).

Cung cấp lớp BaodautuScraper để trích xuất danh sách bài viết qua danh mục HTML
và thu thập toàn bộ nội dung chi tiết bài viết kèm raw capture tầng Bronze.
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from src.core.base_scraper import BaseScraper
from src.core.config import load_watchlist
from src.core.models import VN_TZ, Article
from src.core.tickers import tag_tickers
from src.processor.extractor import extract_text
from src.scrapers import register
from src.scrapers.capture_mixin import CaptureMixin

BASE_URL = "https://baodautu.vn"
SOURCE_DOMAIN = "baodautu.vn"
_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})\b")


def _parse_detail_date(html: str, scope_selector: str) -> str:
    """Trích xuất ngày xuất bản bài viết theo định dạng dd/MM/yyyy HH:mm sang ISO 8601.

    Args:
        html: Mã nguồn HTML bài viết chi tiết.
        scope_selector: CSS selector định vị thẻ chứa chuỗi ngày xuất bản.

    Returns:
        Chuỗi ngày tháng định dạng ISO 8601 múi giờ +07:00, hoặc chuỗi rỗng nếu không tìm thấy.
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


@register("baodautu")
class BaodautuScraper(CaptureMixin, BaseScraper):
    """Bộ thu thập dữ liệu báo Báo Đầu Tư thông qua trích xuất danh mục HTML.

    Attributes:
        categories: Danh sách cấu hình chuyên mục cần thu thập.
        pages_per_cycle: Số trang danh mục cần duyệt trong một chu kỳ.
        item_selector: Bộ chọn CSS xác định khối bài viết.
        link_selector: Bộ chọn CSS xác định liên kết bài viết.
        sapo_selector: Bộ chọn CSS xác định phần tóm tắt ngắn (sapo).
        link_pattern: Mẫu biểu thức chính quy kiểm tra định dạng liên kết bài viết.
        content_selector: Bộ chọn CSS vùng nội dung chi tiết bài viết.
        date_scope: Bộ chọn CSS định vị thời gian đăng bài viết.
        author_selector: Bộ chọn CSS xác định tác giả.
        max_details: Giới hạn số bài viết tải chi tiết trong một chu kỳ.
        base_url: Địa chỉ gốc của trang web báo.
        watchlist: Danh mục mã cổ phiếu cần theo dõi và gán nhãn.
        language: Mã ngôn ngữ nội dung bài viết.
    """

    def __init__(self, config, http, dedup):
        super().__init__(config, http, dedup)
        listing = config.get("listing", {}) or {}
        self.categories = listing.get("categories", [])
        self.pages_per_cycle = listing.get("pages_per_cycle", 1)
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
        """Tạo đường dẫn phân trang cho chuyên mục."""
        return (f"{self.base_url}/{slug}-d{cid}/" if page == 1
                else f"{self.base_url}/{slug}-d{cid}/p{page}")

    def _parse_listing(self, html: str, cat: dict, listing_url: str) -> list[dict]:
        """Phân tích cú pháp HTML danh mục để trích xuất danh sách bài viết.

        Args:
            html: Chuỗi HTML trang danh mục.
            cat: Cấu hình chuyên mục hiện tại.
            listing_url: URL trang danh mục đang xử lý.

        Returns:
            Danh sách từ điển chứa thông tin bài viết thô trích xuất được.
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
                cand_title = a.get_text(" ", strip=True)
                if cand_href and cand_title and self.link_pattern.search(cand_href):
                    href, title = cand_href, cand_title
                    break
            if not href or not title:
                continue
            sapo_node = b.select_one(self.sapo_selector)
            out.append({
                "link": href,
                "title": title,
                "sapo": sapo_node.get_text(" ", strip=True) if sapo_node else "",
                "_cat_name": cat.get("name", ""),
                "_listing_url": listing_url,
            })
        return out

    def fetch_list(self) -> list[dict]:
        """Thu thập danh sách bài viết thô từ các trang danh mục cấu hình.

        Returns:
            Danh sách bài viết thô thu được qua HTTP GET.
        """
        self._details_fetched = 0
        items: list[dict] = []
        for cat in self.categories:
            for page in range(1, self.pages_per_cycle + 1):
                url = self._page_url(cat["slug"], cat["id"], page)
                html = self.http.get(url, referer=f"{self.base_url}/",
                                     timeout=self.config.get("timeout", 30))
                if html is None:
                    self.errors.append(f"listing fetch failed: {url}")
                    continue
                found = self._parse_listing(html, cat, url)
                if not found:
                    self.errors.append(f"listing 0 items (template drift?): {url}")
                items.extend(found)
        return items

    def parse_item(self, raw: dict) -> Article | None:
        """Chuyển đổi từ điển bài viết thô từ danh mục thành đối tượng Article.

        Args:
            raw: Dữ liệu bài viết thô thu thập từ danh mục.

        Returns:
            Đối tượng Article hợp lệ, hoặc None nếu thiếu URL hoặc tiêu đề.
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
                      "listing_url": raw.get("_listing_url", "")},
        )

    # -- detail -------------------------------------------------------------
    def enrich(self, article: Article) -> None:
        """Bổ sung nội dung chi tiết, tác giả, ngày đăng và lưu capture tầng Bronze.

        Args:
            article: Đối tượng Article cần bổ sung thông tin.
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
