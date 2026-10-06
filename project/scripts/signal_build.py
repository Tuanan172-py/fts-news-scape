"""Dựng lại các bảng tín hiệu insight phái sinh từ kết quả mô hình trong DB vận hành."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analytics.signals import build_all                 # noqa: E402
from src.core.config import load_settings                   # noqa: E402
from src.core.stdio import force_utf8_stdio                 # noqa: E402
from src.db.store import ArticleStore                       # noqa: E402

force_utf8_stdio()


def summarize(result: dict[str, list[dict]]) -> list[str]:
    """Tóm tắt số dòng từng bảng và tỷ lệ NULL của từng chỉ số.

    Args:
        result: Kết quả của `build_all`.

    Returns:
        Danh sách dòng văn bản để in.
    """
    daily = result["signal_daily"]
    lines = [f"signal_daily : {len(daily):,} dòng",
             f"entity_links : {len(result['entity_links']):,} dòng",
             f"source_profile: {len(result['source_profile']):,} dòng"]
    if daily:
        cols = ["ama_z", "stale_ratio", "cascade_minutes", "net_sent_story", "net_sent_volume",
                "net_sent_norm", "dispersion", "sent_shift", "coverage_pct"]
        nulls = ", ".join(f"{c}={100.0 * sum(1 for r in daily if r[c] is None) / len(daily):.0f}%"
                          for c in cols)
        lines.append(f"NULL theo chỉ số: {nulls}")
        top = sorted((r for r in daily if r["ama_z"] is not None),
                     key=lambda r: -r["ama_z"])[:10]
        lines.append("Top ama_z:")
        lines += [f"  {r['trade_date']} {r['entity_id']:28} z={r['ama_z']:5.1f} "
                  f"bài={r['n_articles']} nguồn={r['n_sources']} "
                  f"sent_story={r['net_sent_story']}" for r in top]
    return lines


def main(argv: list[str] | None = None) -> int:
    """Chạy dựng bảng tín hiệu và in tóm tắt.

    Args:
        argv: Tham số dòng lệnh; mặc định lấy từ sys.argv.

    Returns:
        Mã thoát 0.
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=30, help="số ngày của cửa sổ dựng lại")
    ap.add_argument("--db", default=None)
    ap.add_argument("--dry-run", action="store_true", help="chỉ tính, không ghi DB")
    args = ap.parse_args(argv)

    db_path = args.db or load_settings()["database"]["path"]
    store = ArticleStore(db_path=db_path)
    started = time.monotonic()
    conn = store._connect()
    try:
        result = build_all(conn, days=args.days, write=not args.dry_run)
    finally:
        conn.close()
    for line in summarize(result):
        print(line)
    print(f"{'dry-run' if args.dry_run else 'đã ghi'} trong {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
