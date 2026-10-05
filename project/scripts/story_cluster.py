"""Cụm hoá bài trùng lặp theo câu chuyện và ghi kết quả kế thừa cho bài chép lại (ADR 0016)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import load_settings
from src.core.stdio import force_utf8_stdio
from src.db.store import ArticleStore
from src.pipeline.cluster_job import refresh

force_utf8_stdio()


def main(argv: list[str] | None = None) -> int:
    """Chạy cụm hoá và kế thừa, hoặc in thống kê hiện có.

    Args:
        argv: Tham số dòng lệnh; mặc định lấy từ sys.argv.

    Returns:
        Mã thoát 0.
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["run", "status"], nargs="?", default="run")
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--db", default=None)
    args = ap.parse_args(argv)
    store = ArticleStore(args.db or load_settings()["database"]["path"])
    conn = store._connect()
    try:
        if args.cmd == "run":
            print(f"[story_cluster] {refresh(conn, args.days)}")
        roles = conn.execute(
            "SELECT role, COUNT(*) FROM cluster_members GROUP BY role").fetchall()
        inh = conn.execute(
            "SELECT COUNT(*) FROM l1_outputs WHERE l1_source='inherited'").fetchone()[0]
        print("cluster_members:", {r[0]: r[1] for r in roles} or "trống", "| đã kế thừa:", inh)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
