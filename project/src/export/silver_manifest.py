"""Xuất danh sách bài viết chuẩn Silver ra tệp CSV manifest."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path

from src.core.models import VN_TZ

EXPORT_DIR = "data/exports"

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
    return (iso or "")[:10]


def query_manifest(
    store, *, today: bool = False, days: int | None = None
) -> list[dict]:
    """Truy vấn danh sách bài viết Silver mới nhất từ cơ sở dữ liệu.

    Args:
        store: Kho dữ liệu cơ sở SQLite.
        today: Chỉ lọc các bài viết được thu thập trong ngày hôm nay.
        days: Số ngày gần nhất cần lấy dữ liệu.

    Returns:
        Danh sách từ điển dữ liệu bài viết chuẩn Silver.
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
    stamp = f"{datetime.now(VN_TZ):%Y%m%d}"
    suffix = "-today" if today else (f"-{days}d" if days else "")
    return Path(EXPORT_DIR) / f"silver-{stamp}{suffix}.csv"


def export_silver_manifest(
    store, *, today: bool = False, days: int | None = None, out: str | None = None
) -> tuple[Path, int]:
    """Xuất danh sách manifest Silver ra tệp CSV với mã hóa UTF-8 BOM.

    Args:
        store: Kho dữ liệu cơ sở SQLite.
        today: Có giới hạn trong ngày hôm nay hay không.
        days: Số ngày gần nhất cần xuất.
        out: Đường dẫn tệp đầu ra tùy chọn.

    Returns:
        Tuple chứa đường dẫn tệp đã xuất và số lượng bài viết.
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
