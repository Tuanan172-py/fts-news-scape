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
        print("usage: l1_ingest.py <output.json | dir> [--no-archive] [--task-dir DIR]")
        return 2

    import argparse
    ap = argparse.ArgumentParser(description="Nạp output tra soát của agent L1")
    ap.add_argument("target", help="output.json hoặc thư mục chứa outputs")
    ap.add_argument("--task-dir", default="data/agent_tasks/l1", help="Thư mục task packets L1 (mặc định: data/agent_tasks/l1)")
    ap.add_argument("--no-archive", action="store_true", help="Không tự động archive task packet khi DoD pass")
    args = ap.parse_args(argv)

    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    runner = L1Runner(ArticleStore(db_path=db_path), task_dir=args.task_dir)
    done = failed = 0
    done_aids: list[str] = []
    for path in _iter_paths(args.target):
        res = runner.ingest_output(str(path))
        if res.get("dod_pass"):
            done += 1
            if res.get("article_id"):
                done_aids.append(res["article_id"])
            print(f"DONE   {res.get('article_id')}")
        else:
            failed += 1
            print(f"FAILED {res.get('article_id')}: {res.get('reasons') or res.get('reason')}")

    if done_aids and not args.no_archive:
        from src.agent.archive import archive_completed_tasks
        archived_cnt = archive_completed_tasks(done_aids, args.task_dir)
        print(f"📦 archived: {archived_cnt}/{len(done_aids)} L1 task packets → {args.task_dir}/archive/")

    print(f"\ningested: done={done} failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
