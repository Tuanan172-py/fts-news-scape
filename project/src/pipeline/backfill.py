"""Backfill discovered URLs and restore lost Bronze files for articles still in the store (rule 10)."""

from __future__ import annotations

import time
from typing import Callable

from loguru import logger

from src.core.config import load_domain_config
from src.db import registry
from src.db.dedup import DedupCache
from src.processor.classifier import classify_rule_based
from src.scrapers import REGISTRY

# Scraper config name for each source domain.
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
    """Build a per-domain scraper factory that shares one HTTP client and one cache.

    Args:
        http: Shared HTTPClient; keeps the per-source rate limits unchanged.
        dedup: DedupCache bound to the store being written.

    Returns:
        Function that takes a domain and returns an initialized scraper, or None when the
        domain has no config.
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
    """Scrape URLs in the discovered state into articles and write them to the store.

    Args:
        store: ArticleStore of the operational DB.
        factory: Per-domain scraper factory from `make_scraper_factory`.
        limit: Maximum number of URLs per run.
        domain: Restrict to one source; None means all sources.
        budget_seconds: Maximum run time; the run stops cleanly once exhausted.
        max_attempts: Maximum attempts before a URL moves to dead_letter.
        clock: Monotonic time function, replaceable in tests.

    Returns:
        Counter dict with keys tried, captured, failed, skipped_no_scraper.
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
            except Exception as e:  # noqa: BLE001 — one failing URL must not stop the whole run
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
    """Re-scrape raw content for stored articles whose Bronze file is lost, then clear the Silver dead-letter.

    Uses the stored title and URL so the new Bronze file carries the same `url_title_hash`.

    Args:
        store: ArticleStore of the operational DB.
        factory: Per-domain scraper factory.
        limit: Maximum number of articles per run.
        budget_seconds: Maximum run time.
        clock: Monotonic time function.

    Returns:
        Counter dict with keys tried, recaptured, failed, skipped_no_scraper.
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
        except Exception as e:  # noqa: BLE001 — one failing article must not stop the whole run
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
