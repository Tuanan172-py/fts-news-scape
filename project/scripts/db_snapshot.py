"""Tạo bản sao chụp cơ sở dữ liệu SQLite tại thời điểm xác định."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import load_settings
from src.core.stdio import force_utf8_stdio
from src.db.snapshot import create_db_snapshot

force_utf8_stdio()


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Tạo snapshot SQLite DB an toàn (Point-in-time)")
    p.add_argument("--src", help="Database nguồn (mặc định theo settings hoặc data/monocle.db)")
    p.add_argument("--out", "-o", default="data/monocle_review.db", help="File snapshot đích")
    args = p.parse_args(argv)

    db_path = args.src or load_settings().get("database", {}).get("path", "data/monocle.db")
    try:
        out_path = create_db_snapshot(src_db_path=db_path, dst_db_path=args.out)
        print(f">>> Snapshot đã tạo thành công tại: {out_path.resolve()}")
        print("    Bạn có thể mở file này bằng DB Browser for SQLite mà không lo làm nghẽn Agents.")
        return 0
    except Exception as e:
        print(f"[!] Lỗi khi tạo snapshot: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
