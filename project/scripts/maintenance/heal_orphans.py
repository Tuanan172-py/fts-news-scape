"""Restore article records missing from the articles table using derived layers."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.core import paths
from src.core.config import load_settings
from src.core.models import Article, sha256_hash
from src.core.stdio import force_utf8_stdio
from src.db.store import ArticleStore

force_utf8_stdio()

_ORPHAN_SQL = """
SELECT DISTINCT x.article_id, w.package_path, w.domain
FROM ({inner}) x
JOIN work_items w ON w.article_id = x.article_id
WHERE NOT EXISTS (SELECT 1 FROM articles a WHERE a.url_title_hash = x.article_id)
"""
_INNER = ("SELECT article_id FROM l1_outputs WHERE dod_pass=1"
          " UNION SELECT article_id FROM agent_outputs WHERE dod_pass=1")


def _title_candidates(pkg: dict, l1_title: str | None) -> list[str]:
    """List candidate titles for an article from its work package.

    Args:
        pkg: Work package dict.
        l1_title: Title recorded in `l1_tasks`, if any.

    Returns:
        Candidate titles: first text line, headings, then the L1 title.
    """
    out = []
    first = (pkg.get("cleaned_text") or "").split("\n", 1)[0].strip()
    if first:
        out.append(first)
    for h in (pkg.get("structure") or {}).get("headings") or []:
        if h.get("text"):
            out.append(str(h["text"]).strip())
    if l1_title:
        out.append(l1_title)
    return out


def _rebuild(pkg: dict, article_id: str, domain: str, l1_title: str | None) -> Article | None:
    """Rebuild an Article from a work package.

    Args:
        pkg: Work package dict.
        article_id: Expected `url_title_hash` of the article.
        domain: Source domain recorded in `work_items`.
        l1_title: Title recorded in `l1_tasks`, if any.

    Returns:
        The rebuilt Article, or None if no title matches the hash.
    """
    url = pkg.get("source_url") or ""
    title = next((t for t in _title_candidates(pkg, l1_title)
                  if sha256_hash(url, t) == article_id), None)
    if not url or not title:
        return None
    text = pkg.get("cleaned_text") or ""
    return Article(
        url=url,
        title=title,
        source_domain=domain or pkg.get("domain") or "",
        content_text=text,
        published_at=pkg.get("published_at") or "",
        fetched_at=(pkg.get("provenance") or {}).get("fetch_ts") or "",
        metadata={"healed_from": "work_package", "raw_sha256": pkg.get("raw_sha256")},
    )


def main(argv: list[str]) -> int:
    """Rebuild orphaned articles from work packages and insert them.

    Args:
        argv: Command-line arguments without the program name.

    Returns:
        Process exit code, always 0.
    """
    ap = argparse.ArgumentParser(description="Khôi phục bài mồ côi từ work-package")
    ap.add_argument("--dry-run", action="store_true", help="Chỉ đếm, không ghi")
    args = ap.parse_args(argv)

    store = ArticleStore(db_path=load_settings()["database"]["path"])
    conn = store.connect()
    try:
        l1_titles = {r["article_id"]: r["title"] for r in conn.execute("SELECT article_id, title FROM l1_tasks")}
        rows = conn.execute(_ORPHAN_SQL.format(inner=_INNER)).fetchall()
    finally:
        conn.close()

    stat, rebuilt = Counter(), []
    for r in rows:
        try:
            pkg = json.loads(paths.resolve_data_path(r["package_path"]).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stat["thiếu/hỏng work-package"] += 1
            continue
        art = _rebuild(pkg, r["article_id"], r["domain"], l1_titles.get(r["article_id"]))
        if art is None:
            stat["không dò ra tiêu đề khớp hash"] += 1
            continue
        rebuilt.append(art)

    stat["dựng lại được"] = len(rebuilt)
    inserted = 0
    if rebuilt and not args.dry_run:
        inserted = store.insert_batch(rebuilt)
        stat["đã ghi vào articles"] = inserted
        stat["bỏ qua do URL đã tồn tại (toà soạn sửa tiêu đề)"] = len(rebuilt) - inserted

    print(f"{'DRY-RUN ' if args.dry_run else ''}mồ côi quét được: {len(rows)}")
    for k, v in stat.most_common():
        print(f"   {v:5}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
