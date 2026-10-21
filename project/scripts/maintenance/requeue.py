"""Return stuck work packages to the `pending` queue.
"""

# Four states used to be dead ends with no way back (`docs/OPEN-ITEMS.md` A0-4):
# `work_items` in `failed`/`held`/`claimed` and `l1_tasks` in `failed`. Fixing the root
# cause did not rescue old articles; manual SQL was required.
#
# Responsibility split from the 2026-09-17 operating decision:
#   - `held` (work_items): automatic after a successful re-derive; this script is not needed.
#   - `claimed`: automatic through the scheduler `reclaim_stale` job.
#   - `failed`: on demand only. The cause usually lies in the article content, so blind
#     retries are wrong. This script handles that case.

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.core.config import load_settings          # noqa: E402
from src.core.stdio import force_utf8_stdio        # noqa: E402
from src.db.store import ArticleStore              # noqa: E402
from src.handoff.catalog import Catalog            # noqa: E402

force_utf8_stdio()


def _requeue_l1(store, limit: int, dry_run: bool) -> int:
    """Reset `l1_tasks` that failed the DoD to `pending` for the next review pass.

    Args:
        store: Article store that provides the database connection.
        limit: Maximum number of tasks to requeue.
        dry_run: Count the candidates without updating.

    Returns:
        Number of tasks found (dry run) or updated.
    """
    conn = store.connect()
    try:
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM l1_tasks WHERE status='failed' ORDER BY id LIMIT ?",
            (limit,)).fetchall()]
        if not ids or dry_run:
            return len(ids)
        marks = ",".join("?" * len(ids))
        cur = conn.execute(
            f"UPDATE l1_tasks SET status='pending' WHERE id IN ({marks})", ids)
        conn.commit()
        return cur.rowcount or 0
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    """Requeue stuck work items and L1 tasks.

    Args:
        argv: Command-line arguments; defaults to `sys.argv[1:]`.

    Returns:
        Process exit code, always 0.
    """
    p = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    p.add_argument("--layer", choices=["gold", "l1", "all"], default="all",
                   help="gold: work_items · l1: l1_tasks · all: cả hai")
    p.add_argument("--state", choices=["failed", "held"], default="failed",
                   help="trạng thái nguồn cần thu hồi (chỉ áp cho work_items)")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--apply", action="store_true",
                   help="thực sự ghi; mặc định chỉ đếm (an toàn theo mặc định)")
    p.add_argument("--db-path", default=None)
    args = p.parse_args(argv)

    store = ArticleStore(args.db_path or load_settings()["database"]["path"])
    dry = not args.apply
    total = 0

    if args.layer in ("gold", "all"):
        n = Catalog(store).requeue(args.state, limit=args.limit, dry_run=dry)
        print(f"work_items {args.state} -> pending: {n}")
        total += n
    if args.layer in ("l1", "all"):
        n = _requeue_l1(store, args.limit, dry)
        print(f"l1_tasks failed -> pending: {n}")
        total += n

    print(f"requeue [{'APPLY' if args.apply else 'DRY-RUN'}]: tổng {total} bản ghi")
    if dry and total:
        print("  Thêm --apply để thực sự đưa về hàng đợi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
