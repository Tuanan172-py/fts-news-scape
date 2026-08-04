"""
Xuất bảng `articles` ra CSV (utf-8-sig → Excel mở tiếng Việt không lỗi font).

Dùng bởi:
- scripts/export_csv.py (CLI thủ công)
- orchestrator (tự động cuối mỗi cycle, mode 'today')

Bỏ cột nặng (content_html/content_text/metadata) — chỉ giữ cột review.
"""

from __future__ import annotations

import csv
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from src.core.models import VN_TZ

DB_PATH = "data/monocle.db"
EXPORT_DIR = "data/exports"

# Thứ tự cột trong CSV.
COLUMNS = [
    "fetched_at", "published_at", "source_domain", "symbols", "categories",
    "sentiment", "sentiment_score", "title", "summary", "url",
]


def _date_prefix(iso: str) -> str:
    """'YYYY-MM-DD' đầu chuỗi ISO (fetched_at/published_at có offset +07:00)."""
    return (iso or "")[:10]


def query_rows(db_path: str = DB_PATH, *, today: bool = False,
               days: int | None = None, domains: list[str] | None = None,
               with_symbols: bool = False, limit: int | None = None) -> list:
    con = sqlite3.connect(db_path)
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


def write_csv(rows: list, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in rows:
            keys = r.keys()
            w.writerow([r[c] if c in keys else "" for c in COLUMNS])


def _auto_name(today: bool, days: int | None) -> Path:
    stamp = f"{datetime.now(VN_TZ):%Y%m%d}"
    suffix = "-today" if today else (f"-{days}d" if days else "")
    return Path(EXPORT_DIR) / f"articles-{stamp}{suffix}.csv"


def export(*, db_path: str = DB_PATH, today: bool = False, days: int | None = None,
           domains: list[str] | None = None, with_symbols: bool = False,
           limit: int | None = None, out: str | None = None,
           verbose: bool = False) -> tuple[Path, int]:
    """Xuất CSV. Trả (đường dẫn, số bài). Không raise lỗi cho caller lo (caller tự bọc)."""
    rows = query_rows(db_path, today=today, days=days, domains=domains,
                      with_symbols=with_symbols, limit=limit)
    out_path = Path(out) if out else _auto_name(today, days)
    write_csv(rows, out_path)

    if verbose:
        by_sent = Counter((r["sentiment"] or "—") for r in rows)
        by_dom = Counter(r["source_domain"] for r in rows)
        print(f">>> Đã xuất {len(rows)} bài → {out_path.resolve()}")
        print("    Sentiment: " + " | ".join(f"{k}={v}" for k, v in by_sent.most_common()))
        print("    Top nguồn: " + " | ".join(f"{k}={v}" for k, v in by_dom.most_common(8)))
    return out_path, len(rows)
