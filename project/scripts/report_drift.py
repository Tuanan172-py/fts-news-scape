"""
report_drift — liệt kê bài bị TEMPLATE_DRIFT / SELECTOR_BROKEN để reconcile (phase-02).

Producer xem list này để sửa selector/extractor TRƯỚC khi agent tiêu thụ package hỏng.

Usage: python scripts/report_drift.py [limit]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import load_settings
from src.core.stdio import force_utf8_stdio
from src.db.store import ArticleStore
from src.pipeline.drift import list_drift

force_utf8_stdio()


def main(argv: list[str]) -> int:
    limit = int(argv[0]) if argv else 100
    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    store = ArticleStore(db_path=db_path)
    rows = list_drift(store, limit=limit)
    if not rows:
        print("Không có bài drift/broken. ✅")
        return 0
    print(f"{'STATE':<16}{'DOMAIN':<16}{'CAPTURED_AT':<26}HASH")
    for r in rows:
        print(
            f"{r['state']:<16}{(r['source_domain'] or ''):<16}"
            f"{(r['captured_at'] or ''):<26}{r['url_title_hash'][:16]}"
        )
    print(
        f"\nTổng: {len(rows)} bài cần reconcile (sửa selector → rederive_from_bronze)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
