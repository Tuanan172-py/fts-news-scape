"""Lớp cơ sở trừu tượng định nghĩa quy trình thu thập dữ liệu theo mẫu Template Method."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from loguru import logger

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

        fuzzy = self.config.get("fuzzy_dedup", True)
        new = []
        for a in articles:
            if self.dedup.is_duplicate(a.url, a.title):
                continue
            if fuzzy and self.dedup.is_similar_title(a.title, self.name):
                logger.debug("[{}] fuzzy-dup skipped: {}", self.name, a.title[:60])
                self.dedup.mark_seen(a.url, a.title, self.name)
                continue
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
