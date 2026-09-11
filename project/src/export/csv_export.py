"""Xuất danh sách bài viết từ cơ sở dữ liệu ra tệp CSV."""

from __future__ import annotations

import csv
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from src.core.models import VN_TZ
from src.core.staging import safe_atomic_write

DB_PATH = "data/monocle.db"
EXPORT_DIR = "data/exports"

# Thứ tự cột trong CSV.
COLUMNS = [
    "fetched_at", "published_at", "source_domain", "symbols", "categories",
    "sentiment", "sentiment_score", "title", "summary", "url",
]


def _date_prefix(iso: str) -> str:
    """Trích xuất tiền tố ngày dạng 'YYYY-MM-DD' từ chuỗi thời gian ISO."""
    return (iso or "")[:10]


def query_rows(db_path: str = DB_PATH, *, today: bool = False,
               days: int | None = None, domains: list[str] | None = None,
               with_symbols: bool = False, limit: int | None = None) -> list:
    """Truy vấn các dòng dữ liệu bài viết theo tiêu chí lọc chỉ định.

    Args:
        db_path: Đường dẫn tới tệp cơ sở dữ liệu SQLite.
        today: Chỉ lấy các bài viết được thu thập trong ngày hôm nay.
        days: Số ngày gần nhất cần lấy dữ liệu.
        domains: Danh sách tên miền nguồn cần lọc.
        with_symbols: Chỉ lấy các bài viết có gắn mã chứng khoán.
        limit: Giới hạn số lượng bản ghi tối đa.

    Returns:
        Danh sách các dòng bản ghi sqlite3.Row tương ứng.
    """
    # Mở mode read-only an toàn để không cạnh tranh lock với writer
    resolved_db = Path(db_path).resolve()
    if resolved_db.exists():
        uri_path = f"file:{resolved_db.as_posix()}?mode=ro"
        con = sqlite3.connect(uri_path, uri=True, timeout=30.0)
    else:
        con = sqlite3.connect(db_path, timeout=30.0)
    con.row_factory = sqlite3.Row
    rows = list(con.execute(
        "SELECT * FROM articles ORDER BY fetched_at DESC, id DESC"))
    con.close()

    if today:
        d = f"{datetime.now(VN_TZ):%Y-%m-%d}"
        rows = [r for r in rows if _date_prefix(r["fetched_at"]) == d]
    elif days:
        cutoff = f"{datetime.now(VN_TZ) - timedelta(days=days):%Y-%m-%d}"
        rows = [r for r in rows if _date_prefix(r["fetched_at"]) >= cutoff]

    if domains:
        want = set(domains)
        rows = [r for r in rows if r["source_domain"] in want]
    if with_symbols:
        rows = [r for r in rows if (r["symbols"] or "").strip()]
    if limit:
        rows = rows[:limit]
    return rows


def write_csv(rows: list, out_path: Path) -> Path:
    """Ghi danh sách bài viết ra tệp CSV với mã hóa UTF-8 BOM.

    Args:
        rows: Danh sách bản ghi dữ liệu cần ghi.
        out_path: Đường dẫn tệp đích.

    Returns:
        Đường dẫn thực tế tới tệp đã lưu thành công.
    """
    def _write(f):
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in rows:
            keys = r.keys()
            w.writerow([r[c] if c in keys else "" for c in COLUMNS])

    final_path, _ = safe_atomic_write(
        out_path,
        _write,
        fallback_on_lock=True,
        encoding="utf-8-sig",
    )
    return final_path


def _auto_name(today: bool, days: int | None) -> Path:
    stamp = f"{datetime.now(VN_TZ):%Y%m%d}"
    suffix = "-today" if today else (f"-{days}d" if days else "")
    return Path(EXPORT_DIR) / f"articles-{stamp}{suffix}.csv"


def export(*, db_path: str = DB_PATH, today: bool = False, days: int | None = None,
           domains: list[str] | None = None, with_symbols: bool = False,
           limit: int | None = None, out: str | None = None,
           verbose: bool = False) -> tuple[Path, int]:
    """Xuất tập dữ liệu bài viết ra tệp CSV qua cơ chế ghi nguyên tử an toàn.

    Args:
        db_path: Đường dẫn cơ sở dữ liệu SQLite.
        today: Có chỉ lọc các bài viết trong ngày hôm nay hay không.
        days: Số ngày gần nhất cần xuất dữ liệu.
        domains: Danh sách tên miền nguồn muốn lọc.
        with_symbols: Có yêu cầu bài viết phải chứa mã chứng khoán hay không.
        limit: Giới hạn số lượng bài viết tối đa.
        out: Đường dẫn tệp đầu ra tùy chỉnh.
        verbose: In thông tin thống kê tóm tắt ra màn hình console.

    Returns:
        Tuple chứa đường dẫn tệp thực tế đã lưu và số lượng bản ghi đã xuất.
    """
    rows = query_rows(db_path, today=today, days=days, domains=domains,
                      with_symbols=with_symbols, limit=limit)
    out_path = Path(out) if out else _auto_name(today, days)
    final_path = write_csv(rows, out_path)

    if verbose:
        by_sent = Counter((r["sentiment"] or "—") for r in rows)
        by_dom = Counter(r["source_domain"] for r in rows)
        print(f">>> Đã xuất {len(rows)} bài → {final_path.resolve()}")
        print("    Sentiment: " + " | ".join(f"{k}={v}" for k, v in by_sent.most_common()))
        print("    Top nguồn: " + " | ".join(f"{k}={v}" for k, v in by_dom.most_common(8)))
    return final_path, len(rows)
