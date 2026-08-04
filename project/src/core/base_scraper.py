"""
BaseScraper — template method pattern (spec §15).

Subclass chỉ implement fetch_list() + parse_item() (+ enrich() tuỳ chọn).
run() là luồng chuẩn: fetch → parse → dedup → enrich → mark seen.
Mọi lỗi được gom vào self.errors, không bao giờ raise ra ngoài
(graceful degradation, spec §4.3). Scraper KHÔNG ghi DB — orchestrator
nhận ScrapeResult.new và enqueue vào DBWriter.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from loguru import logger

from src.core.models import Article, ScrapeResult, now_vn_iso
from src.crawler.http_client import HTTPClient
from src.db.dedup import DedupCache


class BaseScraper(ABC):
    def __init__(self, config: dict, http: HTTPClient, dedup: DedupCache):
        self.config = config
        self.name: str = config["name"]
        self.http = http
        self.dedup = dedup
        self.errors: list[str] = []
        self.disabled: bool = not config.get("enabled", True)

    # -- template method: KHÔNG override ------------------------------------
    def run(self) -> ScrapeResult:
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
                self.dedup.mark_seen(a.url, a.title, self.name)  # không check lại cycle sau
                continue
            new.append(a)

        for a in new:
            try:
                self.enrich(a)
            except Exception as e:
                # enrich fail → giữ article với summary, không bỏ (fallback)
                logger.warning("[{}] enrich failed for {}: {}", self.name, a.url, e)
                self.errors.append(f"enrich {a.url}: {e}")
            a.processed_at = now_vn_iso()
            self.dedup.mark_seen(a.url, a.title, self.name)

        duration = time.monotonic() - started
        logger.info("[{}] cycle done: fetched={} new={} errors={} in {:.1f}s",
                    self.name, len(raw_items), len(new), len(self.errors), duration)
        return ScrapeResult(scraper=self.name, fetched=len(raw_items),
                            new=new, errors=list(self.errors), duration_s=duration)

    # -- hooks cho subclass ---------------------------------------------------
    @abstractmethod
    def fetch_list(self) -> list[dict]:
        """Lấy danh sách item thô từ nguồn (RSS entries / API JSON / HTML)."""

    @abstractmethod
    def parse_item(self, raw: dict) -> Article | None:
        """Chuyển 1 item thô thành Article. Trả None để bỏ qua item."""

    def enrich(self, article: Article) -> None:
        """Hook tuỳ chọn: fetch trang chi tiết, điền content_html/content_text."""
