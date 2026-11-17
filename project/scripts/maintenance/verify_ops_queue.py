"""Verify that ops.db has zero reserved articles in the active queue."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.stdio import force_utf8_stdio
from src.ops.config import resolve_paths
from src.ops.store import OpsStore, RELEASED_WAVE_STATUSES

force_utf8_stdio()


def check_ops_queue() -> bool:
    """Audit the ops.db queue tables and report reservation metrics.

    Returns:
        True if zero articles are reserved; False otherwise.
    """
    paths = resolve_paths()
    ops_db = paths.ops_db

    if not ops_db.exists():
        print(f"Database does not exist at {ops_db}. Queue is empty.")
        print("\nVERDICT: QUEUE UNBLOCKED (0 reserved articles). READY FOR PROCESSING.")
        return True

    conn = sqlite3.connect(f"file:{ops_db}?mode=ro", uri=True)
    try:
        c = conn.cursor()

        status_counts = c.execute(
            "SELECT status, count(*) FROM ops_waves GROUP BY status"
        ).fetchall()
        print("=== OPS WAVES STATUS DISTRIBUTION ===")
        for status, count in status_counts:
            print(f"  {status:<12}: {count:,} waves")

        total_articles = c.execute("SELECT count(*) FROM ops_wave_articles").fetchone()[0]
        distinct_articles = c.execute("SELECT count(DISTINCT article_id) FROM ops_wave_articles").fetchone()[0]
        print("\n=== OPS WAVE ARTICLES INVENTORY ===")
        print(f"  Total historical wave assignments : {total_articles:,}")
        print(f"  Distinct articles ever assigned   : {distinct_articles:,}")

        marks = ",".join("?" * len(RELEASED_WAVE_STATUSES))
        query = (
            "SELECT COUNT(DISTINCT a.article_id) "
            "FROM ops_wave_articles a "
            "JOIN ops_waves w ON w.wave_id = a.wave_id "
            f"WHERE w.status NOT IN ({marks})"
        )
        unreleased_articles = c.execute(query, RELEASED_WAVE_STATUSES).fetchone()[0]
        print("\n=== RESERVATION QUEUE STATUS ===")
        print(f"  Unreleased reserved articles (SQL): {unreleased_articles:,}")

        store = OpsStore(paths.ops_db, log_dir=paths.log_dir)
        store_reserved = store.reserved_article_ids()
        print(f"  Store reserved_article_ids() count : {len(store_reserved):,}")

        if unreleased_articles == 0 and len(store_reserved) == 0:
            print("\nVERDICT: QUEUE UNBLOCKED (0 reserved articles). READY FOR PROCESSING.")
            return True

        print(f"\nVERDICT: BLOCKED ({unreleased_articles} articles still reserved).")
        return False
    finally:
        conn.close()


def main() -> None:
    """Parse arguments and execute queue verification check."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args()
    success = check_ops_queue()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
