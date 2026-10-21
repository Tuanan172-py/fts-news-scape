"""Re-fetch watchlist articles to create a second Bronze capture that change detection can compare."""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

from src.core.models import now_vn_iso
from src.crawler.raw_store import RawStore
from src.crawler.robots import RobotsGate
from src.pipeline.run import process_meta


def select_watchlist(store, *, limit: int = 50, domains: list[str] | None = None) -> list[dict]:
    """Select the newest articles to check for content changes.

    Args:
        store: ArticleStore object connected to the database.
        limit: Maximum number of articles to select.
        domains: Optional domain names to filter by.

    Returns:
        One dict per article with its URL, hash and source domain.
    """
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
    """Derive the matching .meta.json path from a capture result."""
    hp = cap.get("html_path", "")
    return hp[:-5] + ".meta.json" if hp.endswith(".html") else ""


def refresh_row(http, raw_store: RawStore, robots: RobotsGate | None, row: dict,
                *, timeout: int = 30, fetched_at: str | None = None) -> dict:
    """Re-fetch one article and store the new capture in the Bronze layer.

    Args:
        http: HTTP client that requests the page.
        raw_store: RawStore that manages raw file storage.
        robots: Gate that checks robots.txt access; None disables the check.
        row: Article record to re-fetch.
        timeout: Maximum HTTP wait in seconds.
        fetched_at: ISO timestamp of the capture; defaults to the current time.

    Returns:
        Dict with the URL, capture status and path of the new metadata file.
    """
    url = row["url"]
    if robots is not None and not robots.allowed(url):
        return {"url": url, "capture_status": "skipped_robots", "meta_path": ""}
    fetched_at = fetched_at or now_vn_iso()
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
                      respect_robots: bool = True, raw_dir: str | None = None,
                      timeout: int = 30, do_process: bool = True,
                      silver_dir: str | None = None,
                      package_dir: str | None = None) -> dict:
    """Re-fetch the watchlist and trigger the change-detection derivation chain.

    Args:
        store: ArticleStore object that manages the database.
        http: HTTP client that requests pages.
        limit: Maximum number of articles to re-fetch.
        domains: Domain names to filter by.
        respect_robots: Respect robots.txt rules.
        raw_dir: Directory of the raw Bronze data.
        timeout: Network request timeout in seconds.
        do_process: Continue processing into the Silver layer and classification.
        silver_dir: Directory that stores the Silver output.
        package_dir: Directory that stores the hand-off work packages.

    Returns:
        Dict summarizing the re-fetch result and the detected state counts.
    """
    raw_store = RawStore(raw_dir)
    robots = RobotsGate(http) if respect_robots else None
    rows = select_watchlist(store, limit=limit, domains=domains)
    summary = {"selected": len(rows), "refetched": 0, "skipped": 0, "states": {}}
    for row in rows:
        # One failing URL (HTTP or parse) must not abort the whole watchlist.
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
            except Exception as e:  # noqa: BLE001 — non-fatal per article
                logger.error("refresh process fail {}: {}", res["meta_path"], e)
    logger.info("refresh done: {}", summary)
    return summary
