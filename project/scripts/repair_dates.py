"""
One-off: backfill published_at cho bài đã lưu thiếu date (feed date format
phi chuẩn — đã fix parser, bài cũ cần re-map từ feed hiện tại).

Usage: python scripts/repair_dates.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import feedparser
from loguru import logger

from src.core.config import load_domain_config, load_settings, list_domains
from src.core.logging import setup_logging
from src.crawler.http_client import HTTPClient
from src.db.store import ArticleStore
from src.scrapers.rss_generic import _decode_feed, _parse_entry_date

if __name__ == "__main__":
    settings = load_settings()
    setup_logging(settings["logging"]["level"], settings["logging"]["dir"])
    store = ArticleStore(settings["database"]["path"])
    http = HTTPClient(rate_limit_delay=settings["http"]["rate_limit"])

    conn = store._connect()
    missing = {r["url"] for r in conn.execute(
        "SELECT url FROM articles WHERE COALESCE(published_at,'')=''").fetchall()}
    logger.info("{} articles missing published_at", len(missing))

    fixed = 0
    for name in list_domains():
        cfg = load_domain_config(name)
        if cfg.get("method") != "rss":
            continue
        for feed_cfg in cfg.get("rss", {}).get("feeds", []):
            raw = http.get_bytes(feed_cfg["url"])
            if raw is None:
                continue
            for e in feedparser.parse(_decode_feed(raw)).entries:
                link = (e.get("link") or "").strip()
                if link not in missing:
                    continue
                iso = _parse_entry_date(e)
                if iso:
                    conn.execute("UPDATE articles SET published_at=? WHERE url=?",
                                 (iso, link))
                    fixed += 1
    conn.commit()
    conn.close()
    logger.info("Repaired {} / {} missing dates", fixed, len(missing))
