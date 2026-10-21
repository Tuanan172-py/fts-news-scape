"""Export articles from the database to a CSV file."""

from __future__ import annotations

from src.core import paths
import csv
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from src.core.models import VN_TZ
from src.core.staging import safe_atomic_write


# Column order in the CSV.
COLUMNS = [
    "fetched_at", "published_at", "source_domain", "symbols", "categories",
    "sentiment", "sentiment_score", "title", "summary", "url",
]


def _date_prefix(iso: str) -> str:
    """Extract the 'YYYY-MM-DD' date prefix from an ISO timestamp.

    Args:
        iso: ISO timestamp string; None is treated as empty.

    Returns:
        First 10 characters of the timestamp.
    """
    return (iso or "")[:10]


def query_rows(db_path: str | None = None, *, today: bool = False,
               days: int | None = None, domains: list[str] | None = None,
               with_symbols: bool = False, limit: int | None = None) -> list:
    """Query article rows with the given filters.

    Args:
        db_path: Path of the SQLite database file; None uses the operational database.
        today: Keep only articles fetched today.
        days: Number of most recent days to keep.
        domains: Source domains to keep.
        with_symbols: Keep only articles tagged with stock symbols.
        limit: Maximum number of records.

    Returns:
        Matching sqlite3.Row records.
    """
    # Open read-only so the query does not contend for locks with the writer.
    if db_path is None:
        from src.core.config import resolve_db_path
        db_path = str(resolve_db_path())
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
    """Write articles to a CSV file with UTF-8 BOM encoding.

    Args:
        rows: Records to write.
        out_path: Target file path.

    Returns:
        Path of the file actually saved.
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
    """Build the default output path from the date and the filter.

    Args:
        today: Whether the export is limited to today.
        days: Number of most recent days, if any.

    Returns:
        Default CSV path in the exports directory.
    """
    stamp = f"{datetime.now(VN_TZ):%Y%m%d}"
    suffix = "-today" if today else (f"-{days}d" if days else "")
    return paths.exports_dir() / f"articles-{stamp}{suffix}.csv"


def export(*, db_path: str | None = None, today: bool = False, days: int | None = None,
           domains: list[str] | None = None, with_symbols: bool = False,
           limit: int | None = None, out: str | None = None,
           verbose: bool = False) -> tuple[Path, int]:
    """Export the article dataset to a CSV file through a safe atomic write.

    Args:
        db_path: SQLite database path; None uses the operational database.
        today: Keep only articles from today.
        days: Number of most recent days to export.
        domains: Source domains to keep.
        with_symbols: Require articles to carry stock symbols.
        limit: Maximum number of articles.
        out: Custom output file path.
        verbose: Print a summary to the console.

    Returns:
        Tuple of the path of the file saved and the number of records exported.
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
