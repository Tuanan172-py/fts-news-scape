"""
Quality checker — % articles đạt chuẩn spec §4.3 (title + body + date ≥95%).

Usage:
    python scripts/verify_quality.py [source_domain] [--min-body 200]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import load_settings
from src.core.stdio import force_utf8_stdio
from src.db.store import ArticleStore

force_utf8_stdio()


def verify(domain: str | None, min_body: int) -> int:
    store = ArticleStore(load_settings()["database"]["path"])
    conn = store._connect()
    where = "WHERE source_domain = ?" if domain else ""
    args = (domain,) if domain else ()
    rows = conn.execute(
        f"SELECT title, content_text, summary, published_at, source_domain "
        f"FROM articles {where}",
        args,
    ).fetchall()
    conn.close()

    if not rows:
        print(f"No articles found{' for ' + domain if domain else ''}.")
        return 1

    ok = 0
    missing = {"title": 0, "body": 0, "date": 0}
    for r in rows:
        has_title = bool((r["title"] or "").strip())
        body = (r["content_text"] or "").strip() or (r["summary"] or "").strip()
        has_body = len(body) >= min_body
        has_date = bool((r["published_at"] or "").strip())
        if has_title and has_body and has_date:
            ok += 1
        else:
            if not has_title:
                missing["title"] += 1
            if not has_body:
                missing["body"] += 1
            if not has_date:
                missing["date"] += 1

    pct = ok / len(rows) * 100
    print(f"Domain: {domain or 'ALL'}")
    print(f"Articles: {len(rows)} | Quality-OK: {ok} ({pct:.1f}%)")
    print(
        f"Missing — title: {missing['title']}, body(<{min_body}ch): "
        f"{missing['body']}, date: {missing['date']}"
    )
    print("PASS (>=95%)" if pct >= 95 else "FAIL (<95%)")
    return 0 if pct >= 95 else 2


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("domain", nargs="?", default=None)
    p.add_argument("--min-body", type=int, default=200)
    a = p.parse_args()
    sys.exit(verify(a.domain, a.min_body))
