"""Publish the data of a closed day to the SharePoint folder, run with cwd = project/."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.stdio import force_utf8_stdio                         # noqa: E402
from src.export.publisher import PUBLISH_DIR_ENV, parse_day, publish_day  # noqa: E402
from src.db.connect import open_ro  # noqa: E402

force_utf8_stdio()

EXIT_CODES = {"ok": 0, "disabled": 0, "partial": 2}


def _fmt_size(n: int | None) -> str:
    """Format a byte size for the printed table.

    Args:
        n: Size in bytes, or None when unknown.

    Returns:
        Short string such as `12.3 MB`, or `-` when unknown.
    """
    if n is None:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return "-"


def main(argv: list[str]) -> int:
    """Run one publish and print the file table.

    Args:
        argv: Command-line arguments without the program name.

    Returns:
        0 on ok or disabled, 2 on partial, 1 on failed.
    """
    ap = argparse.ArgumentParser(description="Xuất bản một chiều lên SharePoint sandbox (ADR 0026.D1, ADR 0023).")
    ap.add_argument("--date", default="yesterday", help="YYYY-MM-DD hoặc yesterday (mặc định)")
    ap.add_argument("--from-date", help="Ngày bắt đầu backfill (YYYY-MM-DD)")
    ap.add_argument("--to-date", help="Ngày kết thúc backfill (YYYY-MM-DD, mặc định yesterday)")
    ap.add_argument("--dry-run", action="store_true", help="chỉ in kế hoạch tệp, không ghi gì")
    ap.add_argument("--force", action="store_true",
                    help="kiểm và chép lại phần thiếu dù manifest ngày đã đủ; không ghi đè")
    ap.add_argument("--target", help=f"đích dùng thay {PUBLISH_DIR_ENV} cho lần chạy này")
    ap.add_argument("--skip-review", action="store_true",
                    help="bỏ qua review DB snapshot (khuyên dùng khi backfill lịch sử)")
    ap.add_argument("--skip-bronze", action="store_true",
                    help="bỏ qua nén và xuất bản các gói Bronze HTML thô")
    args = ap.parse_args(argv)

    if args.from_date:
        from src.core.config import resolve_db_path

        try:
            start_day = parse_day(args.from_date)
            end_day = parse_day(args.to_date) if args.to_date else parse_day("yesterday")
        except ValueError as e:
            print(f"Lỗi định dạng ngày: {e}")
            return 1

        db = Path(resolve_db_path())
        conn = open_ro(db)
        try:
            cur_rows = conn.execute(
                "SELECT DISTINCT substr(coalesce(nullif(published_at,''), fetched_at), 1, 10) as d "
                "FROM articles "
                "WHERE coalesce(nullif(published_at,''), fetched_at) >= ? "
                "  AND coalesce(nullif(published_at,''), fetched_at) <= ? "
                "ORDER BY d",
                (start_day.isoformat(), end_day.isoformat()),
            ).fetchall()
            target_dates = [parse_day(r[0]) for r in cur_rows if r[0]]
        finally:
            conn.close()

        print(f"Bắt đầu backfill từ {start_day.isoformat()} đến {end_day.isoformat()} "
              f"({len(target_dates)} ngày có dữ liệu)...")
        overall_status = 0
        for cur in target_dates:
            cur_include_review = not args.skip_review
            if cur_include_review and (parse_day("today") - cur).days > 7:
                cur_include_review = False

            print(f"\n--- Xuất bản ngày: {cur.isoformat()} ---")
            res = publish_day(
                cur,
                dry_run=args.dry_run,
                force=args.force,
                target=args.target,
                include_review=cur_include_review,
                include_bronze=not args.skip_bronze,
            )
            print(f"  Trạng thái: {res.status} — {res.message}")
            if res.status == "failed":
                overall_status = 1
        print(f"\nHoàn tất backfill.")
        return overall_status

    try:
        day = parse_day(args.date)
    except ValueError:
        print(f"Ngày không hợp lệ: {args.date}. Dùng YYYY-MM-DD hoặc yesterday.")
        return 1
    res = publish_day(
        day,
        dry_run=args.dry_run,
        force=args.force,
        target=args.target,
        include_review=not args.skip_review,
        include_bronze=not args.skip_bronze,
    )
    print(f"ngày    : {res.day}")
    print(f"đích    : {res.target or '(chưa đặt)'}")
    if res.files:
        width = max(len(f.path) for f in res.files)
        print(f"{'tệp'.ljust(width)}  {'hành động':<9}  {'cỡ':>9}  {'dòng':>7}")
        for f in res.files:
            rows = "-" if f.rows is None else str(f.rows)
            print(f"{f.path.ljust(width)}  {f.action:<9}  {_fmt_size(f.size):>9}  {rows:>7}"
                  + (f"  {f.message}" if f.message else ""))
    if res.pruned:
        print(f"đã xoá review cũ: {', '.join(res.pruned)}")
    if res.manifest:
        print(f"manifest: {res.manifest}")
    print(f"trạng thái: {res.status} — {res.message}")
    return EXIT_CODES.get(res.status, 1)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
