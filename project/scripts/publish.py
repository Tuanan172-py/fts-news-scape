"""Xuất bản dữ liệu của một ngày đã đóng sang thư mục SharePoint, chạy với cwd = project/."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.stdio import force_utf8_stdio                         # noqa: E402
from src.export.publisher import PUBLISH_DIR_ENV, parse_day, publish_day  # noqa: E402

force_utf8_stdio()

EXIT_CODES = {"ok": 0, "disabled": 0, "partial": 2}


def _fmt_size(n: int | None) -> str:
    """Định dạng kích thước byte cho bảng in.

    Args:
        n: Số byte hoặc None.

    Returns:
        Chuỗi ngắn như `12.3 MB`, hoặc `-` khi chưa biết.
    """
    if n is None:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return "-"


def main(argv: list[str]) -> int:
    """Chạy một lần xuất bản và in bảng tệp.

    Args:
        argv: Tham số dòng lệnh, không gồm tên chương trình.

    Returns:
        0 khi ok hoặc disabled, 2 khi partial, 1 khi failed.
    """
    ap = argparse.ArgumentParser(description="Xuất bản một chiều lên SharePoint (ADR 0020).")
    ap.add_argument("--date", default="yesterday", help="YYYY-MM-DD hoặc yesterday (mặc định)")
    ap.add_argument("--dry-run", action="store_true", help="chỉ in kế hoạch tệp, không ghi gì")
    ap.add_argument("--force", action="store_true",
                    help="kiểm và chép lại phần thiếu dù manifest ngày đã đủ; không ghi đè")
    ap.add_argument("--target", help=f"đích dùng thay {PUBLISH_DIR_ENV} cho lần chạy này")
    args = ap.parse_args(argv)

    try:
        day = parse_day(args.date)
    except ValueError:
        print(f"Ngày không hợp lệ: {args.date}. Dùng YYYY-MM-DD hoặc yesterday.")
        return 1
    res = publish_day(day, dry_run=args.dry_run, force=args.force, target=args.target)
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
