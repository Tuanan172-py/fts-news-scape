"""Fill empty `articles.published_at` from the publication time declared in each article's Bronze HTML.

Sitemap backfills built articles from the URL alone and stored no publication time, so they
fell outside the date-scoped waves and landed on their capture day downstream. Dry run by
default; pass --apply to write. Run with cwd = project/.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.core.config import resolve_db_path  # noqa: E402
from src.core.htmldate import extract_published_at  # noqa: E402
from src.core.stdio import force_utf8_stdio  # noqa: E402
from src.crawler.raw_store import RawStore  # noqa: E402

force_utf8_stdio()
BATCH = 500


def main(argv: list[str] | None = None) -> int:
    """Scan undated articles, read their Bronze HTML and fill the publication time.

    Args:
        argv: Command-line arguments; defaults to `sys.argv`.

    Returns:
        0 on success.
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="ghi vào DB; mặc định chỉ đếm")
    ap.add_argument("--db", default=None, help="DB vận hành (mặc định resolve_db_path())")
    args = ap.parse_args(argv)

    db = Path(args.db or resolve_db_path())
    raw = RawStore()
    conn = sqlite3.connect(db, timeout=60)
    rows = conn.execute("SELECT url_title_hash, source_domain, fetched_at FROM articles "
                        "WHERE COALESCE(published_at, '') = ''").fetchall()
    found: list[tuple[str, str]] = []
    stats: Counter = Counter()
    for h, domain, fetched_at in rows:
        html_path, _ = raw.paths_for(domain, h, fetched_at or "")
        try:
            page = Path(html_path).read_bytes()
        except OSError:
            stats[f"{domain}: không có Bronze"] += 1
            continue
        value = extract_published_at(page)
        if not value:
            stats[f"{domain}: trang không khai ngày"] += 1
            continue
        stats[f"{domain}: có ngày"] += 1
        found.append((value, h))
    print(f"Bài thiếu ngày đăng: {len(rows):,}; tìm được ngày: {len(found):,}")
    for key, n in sorted(stats.items()):
        print(f"  {key}: {n:,}")
    if args.apply:
        for i in range(0, len(found), BATCH):
            conn.executemany("UPDATE articles SET published_at = ? WHERE url_title_hash = ? "
                             "AND COALESCE(published_at, '') = ''", found[i:i + BATCH])
            conn.commit()
        print(f"Đã ghi {len(found):,} ngày đăng.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
