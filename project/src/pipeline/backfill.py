"""Cào bù URL đã phát hiện và phục hồi Bronze đã mất cho bài còn trong kho (rule 10)."""

from __future__ import annotations

import time
from typing import Callable

from loguru import logger

from src.core.config import load_domain_config
from src.db import registry
from src.db.dedup import DedupCache
from src.processor.classifier import classify_rule_based
from src.scrapers import REGISTRY

# Tên cấu hình scraper cho từng tên miền nguồn.
CONFIG_BY_DOMAIN = {
    "baodautu.vn": "baodautu",
    "cafef.vn": "cafef",
    "tinnhanhchungkhoan.vn": "tnck",
    "vneconomy.vn": "vneconomy",
    "vietstock.vn": "vietstock",
    "vietnambiz.vn": "vietnambiz",
    "thoibaotaichinhvietnam.vn": "thoibaotaichinhvietnam",
}

ScraperFactory = Callable[[str], object]


def make_scraper_factory(http, dedup: DedupCache) -> ScraperFactory:
    """Tạo hàm dựng scraper theo tên miền, dùng chung HTTP client và bộ nhớ đệm.

    Args:
        http: HTTPClient dùng chung, giữ nguyên giới hạn tốc độ theo nguồn.
        dedup: DedupCache gắn với kho cần ghi.

    Returns:
        Hàm nhận tên miền, trả scraper đã khởi tạo hoặc None khi không có cấu hình.
    """
    cache: dict[str, object] = {}

    def factory(domain: str):
        if domain in cache:
            return cache[domain]
        name = CONFIG_BY_DOMAIN.get(domain)
        scraper = None
        if name:
            try:
                cfg = load_domain_config(name)
                cls = REGISTRY.get(cfg["name"]) or REGISTRY.get(f"_{cfg['method']}")
                scraper = cls(cfg, http, dedup) if cls else None
            except (FileNotFoundError, ValueError, KeyError) as e:
                logger.error("[backfill] cấu hình {} lỗi: {}", name, e)
        cache[domain] = scraper
        return scraper

    return factory


def backfill_pending(store, factory: ScraperFactory, *, limit: int = 100,
                     domain: str | None = None, budget_seconds: float = 600.0,
                     max_attempts: int = 5,
                     clock: Callable[[], float] = time.monotonic) -> dict[str, int]:
    """Cào các URL ở trạng thái discovered thành bài và ghi vào kho.

    Args:
        store: ArticleStore của DB vận hành.
        factory: Hàm dựng scraper theo tên miền, từ `make_scraper_factory`.
        limit: Số URL tối đa mỗi lượt.
        domain: Giới hạn theo nguồn; None là mọi nguồn.
        budget_seconds: Thời gian tối đa của lượt; hết thì dừng sạch.
        max_attempts: Số lần thử tối đa trước khi một URL sang dead_letter.
        clock: Hàm đo thời gian đơn điệu, thay được trong test.

    Returns:
        Từ điển đếm: tried, captured, failed, skipped_no_scraper.
    """
    stats = {"tried": 0, "captured": 0, "failed": 0, "skipped_no_scraper": 0}
    conn = store._connect()
    deadline = clock() + budget_seconds
    try:
        rows = registry.pending(conn, domain, limit)
        for row in rows:
            if clock() >= deadline:
                break
            scraper = factory(row["source_domain"])
            if scraper is None:
                stats["skipped_no_scraper"] += 1
                continue
            stats["tried"] += 1
            try:
                article = scraper.backfill_url(row["first_url"])
            except Exception as e:  # noqa: BLE001 — một URL lỗi không được dừng cả lượt
                registry.mark_failed(conn, row["url_canonical"], f"{type(e).__name__}: {e}",
                                     max_attempts=max_attempts)
                conn.commit()
                stats["failed"] += 1
                continue
            if article is None:
                registry.mark_failed(conn, row["url_canonical"], "không dựng được bài từ URL",
                                     max_attempts=max_attempts)
                conn.commit()
                stats["failed"] += 1
                continue
            for cat in classify_rule_based(article.title, article.content_text):
                if cat not in article.categories and cat != "uncategorized":
                    article.categories.append(cat)
            store.insert_batch([article])
            stats["captured"] += 1
    finally:
        conn.close()
    return stats


def recapture_lost_bronze(store, factory: ScraperFactory, *, limit: int = 100,
                          budget_seconds: float = 600.0,
                          clock: Callable[[], float] = time.monotonic) -> dict[str, int]:
    """Cào lại raw cho bài còn trong kho nhưng đã mất tệp Bronze, rồi gỡ dead-letter Silver.

    Dùng đúng tiêu đề và URL đã lưu để tệp Bronze mới mang cùng `url_title_hash`.

    Args:
        store: ArticleStore của DB vận hành.
        factory: Hàm dựng scraper theo tên miền.
        limit: Số bài tối đa mỗi lượt.
        budget_seconds: Thời gian tối đa của lượt.
        clock: Hàm đo thời gian đơn điệu.

    Returns:
        Từ điển đếm: tried, recaptured, failed, skipped_no_scraper.
    """
    stats = {"tried": 0, "recaptured": 0, "failed": 0, "skipped_no_scraper": 0}
    conn = store._connect()
    deadline = clock() + budget_seconds
    try:
        rows = conn.execute(
            "SELECT meta_path, url_title_hash FROM silver_failures "
            "WHERE dead_letter=1 AND last_error LIKE '%raw_missing%' "
            "ORDER BY fetch_ts DESC LIMIT ?", (limit,)).fetchall()
    finally:
        conn.close()
    for meta_path, h in rows:
        if clock() >= deadline:
            break
        art = store.get_by_hash(h)
        if art is None:
            continue
        scraper = factory(art.source_domain)
        if scraper is None:
            stats["skipped_no_scraper"] += 1
            continue
        stats["tried"] += 1
        if hasattr(scraper, "_details_fetched"):
            scraper._details_fetched = 0
        try:
            scraper.enrich(art)
        except Exception as e:  # noqa: BLE001 — một bài lỗi không được dừng cả lượt
            logger.warning("[recapture] {} lỗi: {}", art.url, e)
            stats["failed"] += 1
            continue
        cap = art.metadata.get("capture") or {}
        if cap.get("capture_status") not in ("ok", "partial"):
            stats["failed"] += 1
            continue
        store.clear_silver_failure(meta_path)
        stats["recaptured"] += 1
    return stats
