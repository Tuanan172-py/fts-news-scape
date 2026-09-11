"""Làm mới và thu thập lại danh sách bài viết theo dõi để phát hiện biến động."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import load_settings
from src.core.stdio import force_utf8_stdio
from src.crawler.http_client import HTTPClient
from src.db.store import ArticleStore
from src.pipeline.refresh import refresh_watchlist

force_utf8_stdio()


import argparse


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Refresh watch-list để kích hoạt change-detection")
    ap.add_argument("limit_pos", nargs="?", type=int, default=None, help="Số lượng bài (tùy chọn)")
    ap.add_argument("domains_pos", nargs="*", default=[], help="Danh sách domain lọc")
    ap.add_argument("-n", "--limit", type=int, default=50, help="Số lượng bài mới nhất (mặc định 50)")
    ap.add_argument("-d", "--domains", nargs="*", default=None, help="Lọc domain")
    args = ap.parse_args(argv)

    limit = args.limit_pos if args.limit_pos is not None else args.limit
    domains = args.domains_pos if args.domains_pos else args.domains

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
