"""Lọc và xóa các bài viết giải trí, đời sống của Yahoo Finance khỏi cơ sở dữ liệu."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.core.config import load_domain_config
from src.core.stdio import force_utf8_stdio

force_utf8_stdio()

DRY = "--dry-run" in sys.argv

cfg = load_domain_config("yahoofinance")
block_terms = [str(t).lower() for t in (cfg.get("filter") or {}).get("none", [])]

c = sqlite3.connect("data/monocle.db")
c.row_factory = sqlite3.Row
rows = c.execute(
    "SELECT id, title, summary FROM articles WHERE source_domain='finance.yahoo.com'"
).fetchall()

to_delete = []
for r in rows:
    hay = f"{r['title']} {r['summary'] or ''}".lower()
    if any(t in hay for t in block_terms):
        to_delete.append(r["id"])
        print(f"[LOẠI] {r['title']}")

print(f"\n{len(to_delete)}/{len(rows)} bài Yahoo bị loại (lifestyle/retail-finance).")
if to_delete and not DRY:
    c.executemany("DELETE FROM articles WHERE id=?", [(i,) for i in to_delete])
    c.commit()
    print(f"Đã xoá {len(to_delete)} bài khỏi DB.")
elif DRY:
    print("(dry-run — chưa xoá)")
