"""Release stale or failed waves in ops.db to unblock reserved articles."""
from __future__ import annotations

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


def release_stale_waves() -> int:
    """Mark abandoned failed and parked waves as CANCELLED to release their articles.

    Returns:
        Number of waves cancelled.
    """
    paths = resolve_paths()
    store = OpsStore(paths.ops_db, log_dir=paths.log_dir)

    with store.conn() as c:
        # Find stale failed or parked waves not opened today.
        rows = c.execute(
            "SELECT wave_id, status FROM ops_waves "
            "WHERE status IN ('FAILED', 'PARKED') "
            "AND wave_id NOT LIKE 'W1023%'"
        ).fetchall()

        if not rows:
            print("Không có wave nào bị kẹt cần giải phóng.")
            return 0

        print(f"Tìm thấy {len(rows)} wave kẹt trong ops.db:")
        for r in rows:
            print(f"  • {r[0]}: {r[1]} -> CANCELLED")

        c.execute(
            "UPDATE ops_waves "
            "SET status = 'CANCELLED', reason = 'Huỷ đợt cũ đã dừng để giải phóng bài tồn đọng' "
            "WHERE status IN ('FAILED', 'PARKED') "
            "AND wave_id NOT LIKE 'W1023%'"
        )

        reserved_left = store.reserved_article_ids()
        print(f"\n✅ Đã chuyển {len(rows)} wave sang CANCELLED.")
        print(f"Số bài còn bị khoá trong hàng đợi: {len(reserved_left):,} bài.")
        return len(rows)


if __name__ == "__main__":
    release_stale_waves()
