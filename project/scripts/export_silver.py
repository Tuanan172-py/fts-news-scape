"""
CLI xuất manifest Silver (danh sách tin cấp Silver) ra CSV.

Logic thật ở src/export/silver_manifest.py (dùng chung với morninger checkpoint).

Usage:
    python scripts/export_silver.py                # toàn bộ Silver → data/exports/silver-YYYYMMDD.csv
    python scripts/export_silver.py --today        # chỉ bài captured hôm nay (giờ VN)
    python scripts/export_silver.py --days 3       # 3 ngày gần nhất (theo captured_at)
    python scripts/export_silver.py --out data/check.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import load_settings
from src.core.stdio import force_utf8_stdio
from src.db.store import ArticleStore
from src.export.silver_manifest import export_silver_manifest

force_utf8_stdio()

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Xuất manifest Silver ra CSV.")
    p.add_argument(
        "--today", action="store_true", help="chỉ bài captured hôm nay (giờ VN)"
    )
    p.add_argument("--days", type=int, help="N ngày gần nhất theo captured_at")
    p.add_argument("--out", help="đường dẫn CSV tuỳ chọn")
    args = p.parse_args()

    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    store = ArticleStore(db_path=db_path)
    path, n = export_silver_manifest(
        store, today=args.today, days=args.days, out=args.out
    )
    print(f">>> Đã xuất {n} bài Silver → {path.resolve()}")
