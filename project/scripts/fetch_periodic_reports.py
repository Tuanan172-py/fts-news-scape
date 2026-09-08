"""
Thu thập báo cáo định kỳ NSO (Cục Thống kê) — design 16.

OFFLINE, opt-in, tần suất thấp. KHÔNG nằm trong cycle 15 phút của orchestrator.
NSO công bố ~ngày 3 hàng tháng lúc ~09:00 (verified 2026-09-07) → lịch khuyến nghị:
cron ngày 2-6 hàng tháng, 2 lần/ngày (08:00 & 14:00 giờ VN), cộng 1 lần/tuần để bắt
báo cáo quý/năm. Xem scripts/run_periodic_reports.ps1.

Usage:
    python scripts/fetch_periodic_reports.py                    # 20 bài mới nhất
    python scripts/fetch_periodic_reports.py --after 2026-08-01 # sync tăng dần
    python scripts/fetch_periodic_reports.py --limit 3
    python scripts/fetch_periodic_reports.py --dry-run          # chỉ discover + parse kỳ
    python scripts/fetch_periodic_reports.py --no-attachments   # bỏ .xlsx/.docx
    python scripts/fetch_periodic_reports.py --list             # xem đã có gì trong DB

Bronze:
    data/raw_reports/nso.gov.vn/<yyyymmdd>/<type>-<period>-r<rev>.html         (+ .meta.json)
    data/raw_reports/nso.gov.vn/<yyyymmdd>/<type>-<period>-r<rev>__<file>.xlsx (+ .binmeta.json)

Root RIENG (khong phai data/raw_html) de pipeline derive/handoff cua bai bao
khong nuot nham bao cao dinh ky - xem design 16 muc 3.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import load_settings
from src.core.logging import setup_logging
from src.core.stdio import force_utf8_stdio
from src.crawler.http_client import HTTPClient
from src.db.store import ArticleStore
from src.pipeline.periodic_reports import SOURCE, PeriodicReportSource

force_utf8_stdio()


def cmd_list(store) -> int:
    conn = store.connect()
    try:
        rows = conn.execute(
            "SELECT report_type, period, revision, published_at, modified_at, "
            "capture_status, attachments_json, title FROM periodic_reports "
            "WHERE source=? ORDER BY period DESC, revision DESC", (SOURCE,)).fetchall()
    finally:
        conn.close()
    if not rows:
        print("(chưa có báo cáo nào trong DB)")
        return 0
    print(f"{'TYPE':<10} {'PERIOD':<9} {'REV':<4} {'PUBLISHED':<20} {'ATT':<4} STATUS")
    print("-" * 78)
    for r in rows:
        n = len(json.loads(r["attachments_json"] or "[]"))
        print(f"{r['report_type']:<10} {r['period']:<9} {r['revision']:<4} "
              f"{(r['published_at'] or '')[:19]:<20} {n:<4} {r['capture_status']}")
    print(f"\nTổng: {len(rows)} bản ghi")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--after", default="", help="ISO date, vd 2026-08-01 (sync tăng dần)")
    p.add_argument("--per-page", type=int, default=20)
    p.add_argument("--pages", type=int, default=1)
    p.add_argument("--limit", type=int, default=0, help="0 = không giới hạn")
    p.add_argument("--no-attachments", action="store_true",
                   help="bỏ qua tải .xlsx/.docx (chỉ Bronze HTML)")
    p.add_argument("--dry-run", action="store_true",
                   help="chỉ discover + parse kỳ, KHÔNG capture, KHÔNG ghi DB")
    p.add_argument("--list", action="store_true", help="liệt kê báo cáo đã có trong DB")
    a = p.parse_args(argv)

    settings = load_settings()
    setup_logging(settings["logging"]["level"], settings["logging"]["dir"])
    store = ArticleStore(settings["database"]["path"])

    if a.list:
        return cmd_list(store)

    http = HTTPClient(rate_limit_delay=settings["http"]["rate_limit"],
                      max_retries=settings["http"]["max_retries"])
    src = PeriodicReportSource(http, store, timeout=settings["http"]["timeout"],
                               fetch_attachments=not a.no_attachments)

    if a.dry_run:
        posts = src.discover(after=a.after, per_page=a.per_page, pages=a.pages)
        print(f"discovered={len(posts)}")
        for post in posts[: (a.limit or len(posts))]:
            ident = src.identify(post)
            title = ((post.get("title") or {}).get("rendered") or "")[:66]
            print(f"  {str(ident):<28} {post.get('date','')[:10]}  {title}")
        if src.errors:
            print("\nerrors:")
            for e in src.errors[:10]:
                print("  -", e)
        return 0

    summary = src.run(after=a.after, per_page=a.per_page, pages=a.pages, limit=a.limit)
    print("periodic-reports: " + " ".join(f"{k}={v}" for k, v in summary.items()))
    if src.errors:
        print(f"errors ({len(src.errors)}):")
        for e in src.errors[:10]:
            print("  -", e)
    # held_unparsed > 0 = có báo cáo không đọc được kỳ → cần người xem lại
    return 1 if summary["held_unparsed"] or summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
