"""
l1_ingest.py — Nạp output tra soát của agent L1 (l1-entity-output-v1).

Với mỗi file output: validate schema + check_l1_dod (grounding + checklist) →
lưu l1_outputs → set l1_tasks.status = done/failed. Idempotent theo article_id.

Chạy sau khi agent (do cron kích hoạt) xử lý các packet trong data/agent_tasks/l1/.

Usage:
    python scripts/l1_ingest.py <output.json | thư_mục>
    python scripts/l1_ingest.py data/agent_outputs_l1/
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.l1_runner import L1Runner
from src.core.config import load_settings
from src.core.stdio import force_utf8_stdio
from src.db.store import ArticleStore

force_utf8_stdio()


def _iter_paths(arg: str):
    p = Path(arg)
    if p.is_dir():
        yield from sorted(p.glob("*.json"))
    else:
        yield p


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: l1_ingest.py <output.json | dir>")
        return 2
    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    runner = L1Runner(ArticleStore(db_path=db_path))
    done = failed = 0
    for path in _iter_paths(argv[0]):
        res = runner.ingest_output(str(path))
        if res.get("dod_pass"):
            done += 1
            print(f"DONE   {res.get('article_id')}")
        else:
            failed += 1
            print(f"FAILED {res.get('article_id')}: {res.get('reasons') or res.get('reason')}")
    print(f"\ningested: done={done} failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
