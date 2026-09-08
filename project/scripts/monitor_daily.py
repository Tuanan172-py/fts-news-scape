"""
monitor_daily.py — CLI điều khiển xuất báo cáo giám sát hệ thống theo mốc thời gian.

Examples:
    python scripts/monitor_daily.py                       # Hôm nay (giờ VN)
    python scripts/monitor_daily.py --date 2026-09-07    # Ngày cụ thể
    python scripts/monitor_daily.py --date yesterday      # Hôm qua
    python scripts/monitor_daily.py --days 7              # 7 ngày gần nhất
    python scripts/monitor_daily.py --save-md             # Vừa in vừa lưu reports/daily/report-YYYY-MM-DD.md
    python scripts/monitor_daily.py --json                # Xuất JSON thô
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Đảm bảo import được src
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.stdio import force_utf8_stdio
from src.monitor.daily_reporter import DailyReporter

force_utf8_stdio()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="News-Scape Daily & Time-sliced Monitor Report")
    parser.add_argument("--date", default="today", help="Mốc ngày (YYYY-MM-DD, today, yesterday, all). Mặc định: today")
    parser.add_argument("--days", type=int, default=0, help="Số ngày quét lùi (ví dụ: 7 = 7 ngày gần nhất tính từ --date)")
    parser.add_argument("--db", default=None, help="Đường dẫn file monocle.db (mặc định lấy từ settings)")
    parser.add_argument("--save-md", action="store_true", help="Lưu báo cáo định dạng Markdown vào reports/daily/")
    parser.add_argument("--out-dir", default="reports/daily", help="Thư mục lưu báo cáo Markdown (mặc định: reports/daily)")
    parser.add_argument("--json", action="store_true", help="In ra JSON thay vì bảng tóm tắt")
    parser.add_argument("--quiet", action="store_true", help="Không in ra console (chỉ lưu file)")
    args = parser.parse_args(argv)

    reporter = DailyReporter(db_path=args.db)
    metrics = reporter.collect_metrics(date_str=args.date, days=args.days)

    if args.json:
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    elif not args.quiet:
        reporter.print_terminal_summary(metrics)

    if args.save_md:
        saved_path = reporter.save_report_markdown(metrics, out_dir=args.out_dir)
        if not args.quiet:
            print(f"-> Đã ghi file báo cáo Markdown tại: {saved_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
