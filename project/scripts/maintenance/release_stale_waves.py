"""Release stale or failed waves in ops.db to unblock reserved articles."""
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
from src.ops.store import OpsStore

force_utf8_stdio()


def release_stale_waves(*, include_active: bool = False) -> int:
    """Mark abandoned failed and parked waves as CANCELLED to release their articles.

    Args:
        include_active: Cancel all non-terminal waves if True; otherwise only FAILED and PARKED.

    Returns:
        Number of waves cancelled.
    """
    paths = resolve_paths()
    store = OpsStore(paths.ops_db, log_dir=paths.log_dir)

    with store.conn() as c:
        if include_active:
            status_clause = "status NOT IN ('DONE', 'CANCELLED')"
        else:
            status_clause = "status IN ('FAILED', 'PARKED')"

        rows = c.execute(
            f"SELECT wave_id, status FROM ops_waves WHERE {status_clause}"
        ).fetchall()

        if not rows:
            print("No stale waves found to release.")
            reserved_left = store.reserved_article_ids()
            print(f"Remaining reserved articles in queue: {len(reserved_left):,}")
            return 0

        print(f"Found {len(rows)} stale waves in ops.db:")
        for r in rows:
            print(f"  * {r[0]}: {r[1]} -> CANCELLED")

        c.execute(
            f"UPDATE ops_waves "
            f"SET status = 'CANCELLED', reason = 'Cancelled stale wave to release backlog articles' "
            f"WHERE {status_clause}"
        )

    reserved_left = store.reserved_article_ids()
    print(f"\nMarked {len(rows)} waves as CANCELLED.")
    print(f"Remaining reserved articles in queue: {len(reserved_left):,}")
    return len(rows)


def main() -> None:
    """Parse command-line arguments and release stale waves."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--all",
        action="store_true",
        help="Release all unfinished waves including stuck active states.",
    )
    args = parser.parse_args()
    release_stale_waves(include_active=args.all)


if __name__ == "__main__":
    main()
