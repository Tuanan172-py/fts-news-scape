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
        print("usage: agent_ingest.py <output.json | dir>")
        return 2
    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    runner = AgentRunner(ArticleStore(db_path=db_path))
    done = failed = 0
    for path in _iter_paths(argv[0]):
        res = runner.ingest_output(str(path))
        if res.get("dod_pass"):
            done += 1
            print(f"DONE   {res['article_id']}")
        else:
            failed += 1
            print(
                f"FAILED {res.get('article_id')}: {res.get('reasons') or res.get('reason')}"
            )
    print(f"\ningested: done={done} failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
