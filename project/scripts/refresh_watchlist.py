"""
Refresh watch-list — re-fetch URL đã biết để kích hoạt change-detection (bug #1).

Ghi Bronze capture thứ 2 (bỏ qua dedup) rồi chạy change-detect + enqueue. Opt-in,
tôn trọng robots + rate limit. Chạy tay hoặc cron riêng (KHÔNG nằm trong hot path).

Usage:
    python scripts/refresh_watchlist.py                 # 50 bài mới nhất
    python scripts/refresh_watchlist.py 100             # 100 bài
    python scripts/refresh_watchlist.py 100 cafef.vn    # lọc domain
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import load_settings
from src.crawler.http_client import HTTPClient
from src.db.store import ArticleStore
from src.pipeline.refresh import refresh_watchlist


def main(argv: list[str]) -> int:
    limit = int(argv[0]) if argv else 50
    domains = argv[1:] or None
    settings = load_settings()
    db_path = settings.get("database", {}).get("path", "data/monocle.db")
    http = HTTPClient(
        rate_limit_delay=settings.get("http", {}).get("rate_limit", 3.0),
        max_retries=settings.get("http", {}).get("max_retries", 3),
    )
    summary = refresh_watchlist(ArticleStore(db_path=db_path), http,
                                limit=limit, domains=domains)
    print(f"refresh: selected={summary['selected']} refetched={summary['refetched']} "
          f"skipped={summary['skipped']} states={summary['states']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
