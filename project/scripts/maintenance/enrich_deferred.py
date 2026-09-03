"""
Enrich các article bị defer detail-fetch (metadata.detail_deferred=true).

Xảy ra khi 1 cycle vượt max_details_per_cycle (thường chỉ lần backfill đầu).
Usage: python scripts/enrich_deferred.py [source_domain] [--limit 100]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

from src.core.config import load_settings
from src.core.logging import setup_logging
from src.core.models import now_vn_iso
from src.crawler.http_client import HTTPClient
from src.db.store import ArticleStore
from src.processor.extractor import extract_content


def main(domain: str | None, limit: int) -> int:
    settings = load_settings()
    setup_logging(settings["logging"]["level"], settings["logging"]["dir"])
    store = ArticleStore(settings["database"]["path"])
    http = HTTPClient(rate_limit_delay=settings["http"]["rate_limit"])

    conn = store._connect()
    where = ("WHERE (metadata_json LIKE '%\"detail_deferred\": true%' "
             "OR metadata_json LIKE '%\"detail_deferred\":true%')")
    if domain:
        where += " AND source_domain = ?"
    rows = conn.execute(
        f"SELECT id, url, metadata_json FROM articles {where} LIMIT ?",
        ((domain, limit) if domain else (limit,))).fetchall()

    logger.info("Found {} deferred articles", len(rows))
    done = 0
    for r in rows:
        result = extract_content(r["url"], html=http.get(r["url"]))
        if result["status"] != "ok" or not result["content"]:
            logger.warning("enrich failed: {}", r["url"])
            continue
        meta = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
        meta.pop("detail_deferred", None)
        conn.execute(
            "UPDATE articles SET content_html=?, content_text=?, "
            "processed_at=?, metadata_json=? WHERE id=?",
            (result["raw_html"], result["content"], now_vn_iso(),
             json.dumps(meta, ensure_ascii=False), r["id"]))
        conn.commit()
        done += 1
    conn.close()
    logger.info("Enriched {}/{} deferred articles", done, len(rows))
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("domain", nargs="?", default=None)
    p.add_argument("--limit", type=int, default=100)
    a = p.parse_args()
    sys.exit(main(a.domain, a.limit))
