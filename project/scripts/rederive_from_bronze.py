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

from src.core.config import load_settings
from src.db.store import ArticleStore
from src.pipeline.run import process_meta

RAW_DIR = Path("data/raw_html")


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

    n = ok = held = 0
    by_state: dict[str, int] = {}
    for meta_path in iter_meta(domain, date):
        n += 1
        try:
            res = process_meta(store, str(meta_path))
        except Exception as e:  # noqa: BLE001
            logger.error("process failed {}: {}", meta_path, e)
            continue
        by_state[res["state"]] = by_state.get(res["state"], 0) + 1
        if res["ok"]:
            ok += 1
        if res.get("enqueue_status") == "held":
            held += 1
    logger.info("re-derive done: {} processed, {} schema-ok, {} held; states={}",
                n, ok, held, by_state)
    print(f"processed={n} schema_ok={ok} held={held} states={by_state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
