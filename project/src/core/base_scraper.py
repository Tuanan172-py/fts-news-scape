"""Lớp cơ sở trừu tượng định nghĩa quy trình thu thập dữ liệu theo mẫu Template Method."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from urllib.parse import urlsplit

from loguru import logger

from src.core.htmltitle import extract_page_title
from src.core.models import Article, ScrapeResult, now_vn_iso
from src.crawler.http_client import HTTPClient
from src.db.dedup import DedupCache


class BaseScraper(ABC):
    """Lớp cơ sở trừu tượng cho các scraper trong hệ thống.

    Attributes:
        config: Cấu hình hoạt động của scraper.
        name: Tên định danh của scraper.
        http: Client HTTP dùng để gửi yêu cầu mạng.
        dedup: Bộ nhớ đệm kiểm tra chống trùng lặp.
        errors: Danh sách lỗi ghi nhận trong chu kỳ hiện tại.
        disabled: Cờ báo trạng thái tạm dừng thu thập.
    """

    def __init__(self, config: dict, http: HTTPClient, dedup: DedupCache):
        self.config = config
        self.name: str = config["name"]
        self.http = http
        self.dedup = dedup
        self.errors: list[str] = []
        self.disabled: bool = not config.get("enabled", True)

    def run(self) -> ScrapeResult:
        """Thực thi chu kỳ thu thập dữ liệu qua các bước chuẩn hóa.

        Returns:
            Đối tượng ScrapeResult chứa danh sách bài viết mới và thống kê lỗi.
        """
        self.errors = []
        started = time.monotonic()
        if self.disabled:
            logger.info("[{}] disabled, skipping", self.name)
            return ScrapeResult(scraper=self.name)

        try:
            raw_items = self.fetch_list()
        except Exception as e:
            logger.error("[{}] fetch_list failed: {}", self.name, e)
            self.errors.append(f"fetch_list: {e}")
            raw_items = []

        articles: list[Article] = []
        for raw in raw_items:
            try:
                a = self.parse_item(raw)
            except Exception as e:
                logger.warning("[{}] parse_item failed: {}", self.name, e)
                self.errors.append(f"parse_item: {e}")
                continue
            if a:
                articles.append(a)

        # Rule 10 (ADR 0013): ghi sổ phát hiện TRƯỚC mọi bước lọc, và chỉ bỏ bản sao kỹ thuật.
        # Trùng ngữ nghĩa là việc của bước cụm hoá sau Bronze, không bao giờ loại bài ở đây.
        via = self.config.get("discovery_via", "listing")
        new = []
        seen_keys: set[str] = set()
        for a in articles:
            key, _is_new, alias_form = self.dedup.discover(a.url, a.source_domain or self.name, via)
            # Hash đã thấy chỉ đủ để bỏ qua khi sổ phát hiện xác nhận bài đã vào kho. Bài từng bị
            # đánh dấu đã thấy mà chưa có dòng `articles` (lọc mờ cũ) được lấy lại.
            if self.dedup.is_duplicate(a.url, a.title) and (not key or self.dedup.is_captured(key)):
                continue
            if key and (key in seen_keys or (alias_form and self.dedup.is_captured(key))):
                logger.debug("[{}] url alias skipped: {}", self.name, a.url[:80])
                continue
            if key:
                seen_keys.add(key)
            new.append(a)

        for a in new:
            try:
                self.enrich(a)
            except Exception as e:
                logger.warning("[{}] enrich failed for {}: {}", self.name, a.url, e)
                self.errors.append(f"enrich {a.url}: {e}")
            a.processed_at = now_vn_iso()
            # Đánh dấu đã xem được thực hiện cùng transaction ghi bài viết vào cơ sở dữ liệu.

        duration = time.monotonic() - started
        logger.info("[{}] cycle done: fetched={} new={} errors={} in {:.1f}s",
                    self.name, len(raw_items), len(new), len(self.errors), duration)
        return ScrapeResult(scraper=self.name, fetched=len(raw_items),
                            new=new, errors=list(self.errors), duration_s=duration)

    @abstractmethod
    def fetch_list(self) -> list[dict]:
        """Lấy danh sách các bản ghi thô từ nguồn dữ liệu.

        Returns:
            Danh sách các bản ghi thô dạng dictionary.
        """

    @abstractmethod
    def parse_item(self, raw: dict) -> Article | None:
        """Phân tích một bản ghi thô thành đối tượng Article.

        Args:
            raw: Bản ghi thô thu thập từ nguồn.

        Returns:
            Đối tượng Article đã phân tích hoặc None nếu bản ghi không hợp lệ.
        """

    def enrich(self, article: Article) -> None:
        """Bổ sung nội dung chi tiết cho bài viết từ trang nguồn.

        Args:
            article: Đối tượng Article cần bổ sung nội dung.
        """

    def article_from_url(self, url: str) -> Article | None:
        """Dựng Article tối thiểu từ một URL bằng cách đọc tiêu đề trang chi tiết.

        Args:
            url: URL bài viết do sổ phát hiện hoặc kênh đối chiếu cung cấp.

        Returns:
            Article có tiêu đề hợp lệ, hoặc None khi không tải được hay không tìm ra tiêu đề.
        """
        host = urlsplit(url).netloc.lower().removeprefix("www.")
        html = self.http.get(url, referer=f"https://{host}/",
                             timeout=self.config.get("timeout", 30))
        if not html:
            return None
        title = extract_page_title(html)
        if not title:
            return None
        return Article(url=url, title=title, source_domain=host,
                       metadata={"language": self.config.get("language", "vi"),
                                 "backfill": True})

    def backfill_url(self, url: str) -> Article | None:
        """Cào một bài theo URL qua đúng đường enrich và Bronze của scraper này.

        Args:
            url: URL bài viết cần lấy.

        Returns:
            Article đã bổ sung nội dung và `processed_at`, hoặc None khi không dựng được bài.
        """
        article = self.article_from_url(url)
        if article is None:
            return None
        if hasattr(self, "_details_fetched"):
            self._details_fetched = 0
        try:
            self.enrich(article)
        except Exception as e:
            logger.warning("[{}] backfill enrich failed for {}: {}", self.name, url, e)
            self.errors.append(f"backfill enrich {url}: {e}")
        article.processed_at = now_vn_iso()
        return article
