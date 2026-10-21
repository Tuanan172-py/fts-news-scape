"""Export the Silver-layer article list to a CSV manifest file."""

from __future__ import annotations

from src.core import paths
import csv
from datetime import datetime, timedelta
from pathlib import Path

from src.core.models import VN_TZ

COLUMNS = [
    "article_id",
    "domain",
    "source_url",
    "title",
    "published_at",
    "captured_at",
    "state",
    "recommendation",
    "work_status",
]

_SQL = """
SELECT
  v.url_title_hash AS article_id,
  v.source_domain AS domain,
  a.url AS source_url,
  a.title AS title,
  a.published_at AS published_at,
  v.captured_at AS captured_at,
  v.state AS state,
  v.recommendation AS recommendation,
  w.status AS work_status
FROM article_versions v
JOIN (SELECT url_title_hash, MAX(id) AS max_id
      FROM article_versions GROUP BY url_title_hash) l
  ON v.id = l.max_id
LEFT JOIN articles a ON a.url_title_hash = v.url_title_hash
LEFT JOIN work_items w ON w.article_id = v.url_title_hash
     AND w.raw_sha256 = v.content_sha256
ORDER BY v.captured_at DESC
"""


def _date_prefix(iso: str) -> str:
    """Extract the 'YYYY-MM-DD' date prefix from an ISO timestamp.

    Args:
        iso: ISO timestamp string; None is treated as empty.

    Returns:
        First 10 characters of the timestamp.
    """
    return (iso or "")[:10]


def query_manifest(
    store, *, today: bool = False, days: int | None = None
) -> list[dict]:
    """Query the latest Silver-layer articles from the database.

    Args:
        store: SQLite data store.
        today: Keep only articles captured today.
        days: Number of most recent days to keep.

    Returns:
        Silver-layer article data dicts.
    """
    conn = store.connect()
    try:
        rows = [dict(r) for r in conn.execute(_SQL).fetchall()]
    finally:
        conn.close()
    if today:
        d = f"{datetime.now(VN_TZ):%Y-%m-%d}"
        rows = [r for r in rows if _date_prefix(r["captured_at"]) == d]
    elif days:
        cutoff = f"{datetime.now(VN_TZ) - timedelta(days=days):%Y-%m-%d}"
        rows = [r for r in rows if _date_prefix(r["captured_at"]) >= cutoff]
    return rows


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
    return paths.exports_dir() / f"silver-{stamp}{suffix}.csv"


def export_silver_manifest(
    store, *, today: bool = False, days: int | None = None, out: str | None = None
) -> tuple[Path, int]:
    """Export the Silver manifest list to a CSV file with UTF-8 BOM encoding.

    Args:
        store: SQLite data store.
        today: Limit the export to today.
        days: Number of most recent days to export.
        out: Optional output file path.

    Returns:
        Tuple of the exported file path and the article count.
    """
    rows = query_manifest(store, today=today, days=days)
    out_path = Path(out) if out else _auto_name(today, days)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow([r.get(c) or "" for c in COLUMNS])
    return out_path, len(rows)
