"""Xuất danh sách bài viết từ cơ sở dữ liệu ra tệp CSV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.stdio import force_utf8_stdio
from src.export.csv_export import export

force_utf8_stdio()

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Xuất articles ra CSV để kiểm tra.")
    p.add_argument(
        "--today", action="store_true", help="chỉ bài fetch hôm nay (giờ VN)"
    )
    p.add_argument("--days", type=int, help="N ngày gần nhất theo fetched_at")
    p.add_argument(
        "--domain", nargs="+", dest="domains", help="lọc theo nguồn (vd: cafef fireant)"
    )
    p.add_argument(
        "--with-symbols",
        action="store_true",
        dest="with_symbols",
        help="chỉ bài có gắn mã CK",
    )
    p.add_argument("--limit", type=int, help="giới hạn số bài")
    p.add_argument("--out", help="đường dẫn CSV tuỳ chọn")
    args = p.parse_args()
    export(
        today=args.today,
        days=args.days,
        domains=args.domains,
        with_symbols=args.with_symbols,
        limit=args.limit,
        out=args.out,
        verbose=True,
    )
