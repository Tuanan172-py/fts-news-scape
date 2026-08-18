"""
Refresh watch-list — CHỦ ĐỘNG re-fetch URL đã biết để KÍCH HOẠT change-detection (bug #1).

Vấn đề gốc: dedup (`seen_articles`) chặn re-scrape cùng URL ở hot path → mỗi bài chỉ có
1 lần capture → các state CONTENT_CHANGED/TEMPLATE_DRIFT/SELECTOR_BROKEN không bao giờ
kích hoạt ("machinery ngủ"). Driver này re-fetch một watch-list (BỎ QUA dedup), ghi Bronze
capture thứ 2, rồi chạy `process_meta` → so sánh version trước ⇒ change-detection hoạt động.

OFFLINE, opt-in (chạy tay / cron riêng). Tôn trọng robots + rate limit. KHÔNG sửa hot path.
Xem docs/design/07 (change-detection) và issue #1.
"""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

from src.core.models import now_vn_iso
from src.crawler.raw_store import RawStore
from src.crawler.robots import RobotsGate
from src.pipeline.run import process_meta


def select_watchlist(store, *, limit: int = 50, domains: list[str] | None = None) -> list[dict]:
    """URL đã biết cần refresh (mặc định: bài mới nhất — dễ thay đổi nội dung nhất)."""
    conn = store.connect()
    try:
        sql = "SELECT url, url_title_hash, source_domain FROM articles"
        params: list = []
        if domains:
            sql += " WHERE source_domain IN (%s)" % ",".join("?" for _ in domains)
            params += list(domains)
        sql += " ORDER BY fetched_at DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _meta_path_of(cap: dict) -> str:
    hp = cap.get("html_path", "")
    return hp[:-5] + ".meta.json" if hp.endswith(".html") else ""


def refresh_row(http, raw_store: RawStore, robots: RobotsGate | None, row: dict,
                *, timeout: int = 30, fetched_at: str | None = None) -> dict:
    """Re-fetch 1 URL → ghi Bronze capture mới. Trả {url, capture_status, meta_path}."""
    url = row["url"]
    if robots is not None and not robots.allowed(url):
        return {"url": url, "capture_status": "skipped_robots", "meta_path": ""}
    fetched_at = fetched_at or now_vn_iso()
    # Fix C: đã có capture HÔM NAY cho bài này → KHÔNG re-fetch/ghi đè (giữ Bronze,
    # tránh os.replace lock, và so-với-chính-mình vô nghĩa).
    html_path, meta_path = raw_store.paths_for(row["source_domain"],
                                               row["url_title_hash"], fetched_at)
    if os.path.exists(html_path):
        return {"url": url, "capture_status": "skipped_exists",
                "meta_path": meta_path if os.path.exists(meta_path) else ""}
    if hasattr(http, "rate_limiter"):
        http.rate_limiter.wait(url)
    resp = http.get_response(url, timeout=timeout)
    cap = raw_store.save(row["source_domain"], url, row["url_title_hash"], resp,
                         fetched_at=fetched_at)
    return {"url": url, "capture_status": cap["capture_status"],
            "meta_path": _meta_path_of(cap)}


def refresh_watchlist(store, http, *, limit: int = 50, domains: list[str] | None = None,
                      respect_robots: bool = True, raw_dir: str = "data/raw_html",
                      timeout: int = 30, do_process: bool = True,
                      silver_dir: str = "data/silver",
                      package_dir: str = "data/work_packages") -> dict:
    """Re-fetch watch-list → Bronze capture thứ 2 → process_meta (change-detect + enqueue)."""
    raw_store = RawStore(raw_dir)
    robots = RobotsGate(http) if respect_robots else None
    rows = select_watchlist(store, limit=limit, domains=domains)
    summary = {"selected": len(rows), "refetched": 0, "skipped": 0, "states": {}}
    for row in rows:
        # Fix B: 1 URL lỗi (HTTP/parse) KHÔNG được làm sập cả watch-list.
        try:
            res = refresh_row(http, raw_store, robots, row, timeout=timeout)
        except Exception as e:  # noqa: BLE001 — non-fatal per URL
            logger.error("[refresh] fetch fail {}: {}", row.get("url"), e)
            summary["skipped"] += 1
            continue
        if res["capture_status"] not in ("ok", "partial"):
            summary["skipped"] += 1
            continue
        summary["refetched"] += 1
        if do_process and res["meta_path"] and Path(res["meta_path"]).exists():
            try:
                out = process_meta(store, res["meta_path"], silver_dir=silver_dir,
                                   package_dir=package_dir)
                st = out.get("state", "?")
                summary["states"][st] = summary["states"].get(st, 0) + 1
            except Exception as e:  # noqa: BLE001 — non-fatal per bài
                logger.error("refresh process fail {}: {}", res["meta_path"], e)
    logger.info("refresh done: {}", summary)
    return summary
