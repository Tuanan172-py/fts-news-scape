"""
dbq.py — Chạy nhanh 1 câu SQL trên monocle.db. MẶC ĐỊNH READ-ONLY (an toàn).

Tránh khổ escape dấu nháy như `python -c`; mở chế độ mode=ro nên KHÔNG thể lỡ tay sửa DB.
Ghi chỉ khi có --allow-write (nên backup trước).

Usage:
    python scripts/dbq.py "select status,count(*) n from work_items group by status"
    python scripts/dbq.py "select * from articles order by fetched_at desc limit 5" --limit 5
    python scripts/dbq.py "update l1_outputs set dod_pass=0 where article_id='x'" --allow-write
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import load_settings          # noqa: E402
from src.core.stdio import force_utf8_stdio        # noqa: E402

force_utf8_stdio()

_WRITE_KW = ("insert", "update", "delete", "drop", "alter", "create", "replace", "truncate", "pragma")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sql")
    ap.add_argument("--db", default=None)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--allow-write", action="store_true", help="cho phép câu lệnh ghi (nguy hiểm)")
    a = ap.parse_args(argv)

    db = a.db or load_settings().get("database", {}).get("path", "data/monocle.db")
    is_write = a.sql.strip().lower().startswith(_WRITE_KW)
    if is_write and not a.allow_write:
        print("TỪ CHỐI: câu lệnh có vẻ GHI dữ liệu. Thêm --allow-write nếu chắc chắn (nên backup trước).")
        return 2

    if a.allow_write:
        con = sqlite3.connect(db)
    else:
        con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)   # read-only cứng
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(a.sql)
        if a.allow_write:
            con.commit()
            print(f"OK — rows_affected={cur.rowcount}")
            return 0
        rows = cur.fetchmany(a.limit)
        if not rows:
            print("(0 dòng)")
            return 0
        cols = list(rows[0].keys())
        print(" | ".join(cols))
        print("-" * 60)
        for r in rows:
            print(" | ".join("" if r[c] is None else str(r[c]) for c in cols))
        if len(rows) == a.limit:
            print(f"... (đã cắt ở {a.limit} dòng; dùng --limit N để lấy thêm)")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
