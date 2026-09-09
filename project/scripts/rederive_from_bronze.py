"""
Re-derive Silver + version + work-package + catalog từ WORM Bronze (offline, idempotent).

Đây là driver chính của downstream pipeline (thay cho build_silver + enqueue_pending):
sửa parser / bump schema → chạy lại KHÔNG cần re-scrape (raw bất biến = source of truth).

Usage:
    python scripts/rederive_from_bronze.py                 # tất cả Bronze
    python scripts/rederive_from_bronze.py cafef.vn        # 1 domain
    python scripts/rederive_from_bronze.py cafef.vn 20260813
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

from src.core.config import load_settings, resolve_project_path
from src.core.stdio import force_utf8_stdio
from src.db.store import ArticleStore
from src.pipeline.run import process_meta

force_utf8_stdio()

RAW_DIR = resolve_project_path("data/raw_html")


def iter_meta(domain: str | None, date: str | None):
    root = RAW_DIR / domain if domain else RAW_DIR
    if domain and date:
        root = RAW_DIR / domain / date
    if not root.exists():
        return
    yield from root.rglob("*.meta.json")


def main(argv: list[str]) -> int:
    domain = argv[0] if len(argv) > 0 else None
    date = argv[1] if len(argv) > 1 else None
    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    store = ArticleStore(db_path=db_path)

    logger.info("Scanning Bronze meta files (domain={}, date={})...", domain or "all", date or "all")
    meta_files = list(iter_meta(domain, date))
    total = len(meta_files)
    logger.info("Found {} meta files. Starting re-derive processing...", total)

    ok = held = failed = 0
    by_state: dict[str, int] = {}
    for i, meta_path in enumerate(meta_files, 1):
        try:
            res = process_meta(store, str(meta_path))
        except Exception as e:  # noqa: BLE001
            logger.error("process failed {}: {}", meta_path, e)
            failed += 1
            by_state["exception"] = by_state.get("exception", 0) + 1
            continue

        state = res.get("state", "failed" if not res.get("ok") else "unknown")
        by_state[state] = by_state.get(state, 0) + 1
        if res.get("ok"):
            ok += 1
        else:
            failed += 1
        if res.get("enqueue_status") == "held":
            held += 1

        if i % 50 == 0 or i == total:
            pct = (i / total * 100) if total else 100.0
            logger.info("Progress: [{}/{}] ({:.1f}%) | ok={} held={} failed={} | latest: {}",
                        i, total, pct, ok, held, failed, state)

    logger.info("re-derive done: {} processed, {} schema-ok, {} held, {} failed; states={}",
                total, ok, held, failed, by_state)
    print(f"processed={total} schema_ok={ok} held={held} failed={failed} states={by_state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
