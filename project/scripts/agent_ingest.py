"""
Nạp agent-output-v1 do agent NGOÀI sinh ra (Vòng 3 infra, không LLM).

Với mỗi file output: verify preconditions → validate schema → check DoD →
lưu agent_outputs → mark_done (đạt) / mark_failed (không đạt). Idempotent.

Usage:
    python scripts/agent_ingest.py output.json           # 1 file
    python scripts/agent_ingest.py data/agent_outputs_in # cả thư mục *.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.runner import AgentRunner
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
        print("usage: agent_ingest.py <output.json | dir> [--no-archive] [--task-dir DIR]")
        return 2

    import argparse
    ap = argparse.ArgumentParser(description="Nạp agent-output-v1 do agent NGOÀI sinh ra")
    ap.add_argument("target", help="output.json hoặc thư mục chứa outputs")
    ap.add_argument("--task-dir", default="data/agent_tasks", help="Thư mục task packets (mặc định: data/agent_tasks)")
    ap.add_argument("--no-archive", action="store_true", help="Không tự động archive task packet khi DoD pass")
    args = ap.parse_args(argv)

    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    runner = AgentRunner(ArticleStore(db_path=db_path), task_dir=args.task_dir)
    done = failed = 0
    from src.agent.batch_handoff import unpack_batch_output

    for path in _iter_paths(args.target):
        unpacked_items = unpack_batch_output(path)
        if not unpacked_items:
            res = runner.ingest_output(str(path))
            unpacked_items = [res] if res.get("article_id") else []

        for item in unpacked_items:
            res = runner.ingest_output(item) if not isinstance(item, dict) or "dod_pass" not in item else item
            if res.get("dod_pass"):
                done += 1
                if res.get("article_id"):
                    done_aids.append(res["article_id"])
                print(f"DONE   {res['article_id']}")
            else:
                failed += 1
                print(
                    f"FAILED {res.get('article_id')}: {res.get('reasons') or res.get('reason')}"
                )

    if done_aids and not args.no_archive:
        from src.agent.archive import archive_completed_tasks
        archived_cnt = archive_completed_tasks(done_aids, args.task_dir)
        print(f"📦 archived: {archived_cnt}/{len(done_aids)} task packets → {args.task_dir}/archive/")

    print(f"\ningested: done={done} failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
