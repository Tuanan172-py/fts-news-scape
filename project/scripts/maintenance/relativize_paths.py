"""
relativize_paths.py — Đổi `l1_tasks.packet_path` và `work_items.package_path` từ đường dẫn
TUYỆT ĐỐI sang tương đối theo PROJECT_ROOT.

Vì sao: repo được dùng trên 2 máy với 2 tên user khác nhau. Đo trên monocle.db 2026-09-07:
1.364 dòng `C:/Users/anpt/...` và 423 dòng `C:/Users/An Thanh Pham/...` — mỗi máy chỉ mở
được phần đường dẫn của chính nó, phần còn lại hỏng im lặng.

Chỉ cắt phần TRƯỚC thư mục `project/`; không đụng dòng đã tương đối. Chạy lại nhiều lần vô hại.

Usage:
    python scripts/maintenance/relativize_paths.py --dry-run
    python scripts/maintenance/relativize_paths.py
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.core.config import load_settings
from src.core.stdio import force_utf8_stdio
from src.db.store import ArticleStore

force_utf8_stdio()

# ".../<bat ky>/project/data/agent_tasks/l1/x.json" -> "data/agent_tasks/l1/x.json"
_ABS_RE = re.compile(r"^.*[\\/]project[\\/]", re.IGNORECASE)

_TARGETS = (("l1_tasks", "packet_path"), ("work_items", "package_path"))


def _relativize(value: str) -> str | None:
    """Trả bản tương đối, hoặc None nếu không cần đổi."""
    if not value or not _ABS_RE.match(value):
        return None
    return _ABS_RE.sub("", value).replace("\\", "/")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Chuẩn hoá đường dẫn tuyệt đối trong monocle.db")
    ap.add_argument("--dry-run", action="store_true", help="Chỉ đếm, không ghi")
    args = ap.parse_args(argv)

    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    conn = ArticleStore(db_path=db_path).connect()
    try:
        total = 0
        for table, column in _TARGETS:
            rows = conn.execute(
                f"SELECT rowid AS rid, {column} FROM {table} WHERE {column} IS NOT NULL").fetchall()
            updates = [(new, r["rid"]) for r in rows
                       if (new := _relativize(r[column])) is not None]
            print(f"{table}.{column}: {len(updates)}/{len(rows)} dòng cần đổi")
            if updates and not args.dry_run:
                conn.executemany(f"UPDATE {table} SET {column}=? WHERE rowid=?", updates)
                conn.commit()
            total += len(updates)
        print(f"{'DRY-RUN ' if args.dry_run else ''}tổng: {total} dòng")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
