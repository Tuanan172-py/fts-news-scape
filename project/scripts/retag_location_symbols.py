"""Gỡ mã cổ phiếu bị gán nhầm từ ngữ cảnh địa danh khỏi cột articles.symbols."""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.tickers import _TICKER_RE, is_location_context  # noqa: E402

DEFAULT_DB = Path(r"C:\data\news-scape\monocle.db")
LOG_DIR = Path(__file__).resolve().parents[1] / "data" / "state"


def location_only_codes(symbols: str, text: str) -> list[str]:
    """Tìm các mã trong symbols mà mọi lần xuất hiện trong văn bản đều là địa danh.

    Args:
        symbols: Chuỗi mã ngăn cách bằng dấu phẩy.
        text: Tiêu đề và tóm tắt của bài.

    Returns:
        Danh sách mã cần gỡ. Mã không xuất hiện trong văn bản được giữ nguyên.
    """
    out = []
    for code in filter(None, symbols.split(",")):
        hits = [m for m in _TICKER_RE.finditer(text) if m.group() == code]
        if hits and all(is_location_context(text, m.start(), m.end()) for m in hits):
            out.append(code)
    return out


def main() -> int:
    """Chạy thử hoặc áp dụng việc gỡ mã gán nhầm và ghi nhật ký hoàn tác.

    Returns:
        Mã thoát 0 khi thành công.
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--apply", action="store_true", help="ghi vào DB (mặc định chỉ chạy thử)")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    rows = con.execute(
        "SELECT id, symbols, title, COALESCE(summary, '') FROM articles "
        "WHERE symbols IS NOT NULL AND symbols != ''").fetchall()
    changes = []
    for aid, symbols, title, summary in rows:
        bad = location_only_codes(symbols, f"{title} {summary}")
        if bad:
            new = ",".join(s for s in symbols.split(",") if s and s not in bad)
            changes.append((aid, symbols, new, ",".join(bad)))

    removed: dict[str, int] = {}
    for *_, bad in changes:
        for code in bad.split(","):
            removed[code] = removed.get(code, 0) + 1
    print(f"bài cần sửa: {len(changes)} · mã gỡ: {removed}")
    if not args.apply:
        print("chạy thử, chưa ghi. Thêm --apply để ghi.")
        return 0

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = LOG_DIR / f"retag_location_symbols_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with log.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["article_id", "symbols_old", "symbols_new", "removed"])
        w.writerows(changes)
    with con:
        con.executemany("UPDATE articles SET symbols = ? WHERE id = ?",
                        [(new, aid) for aid, _, new, _ in changes])
    print(f"đã ghi {len(changes)} bài · nhật ký hoàn tác: {log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
