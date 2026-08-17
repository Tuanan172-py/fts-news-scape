"""
Xuất task-packet cho agent NGOÀI (Vòng 3 infra, không LLM).

Claim work_items pending → ghi data/agent_tasks/<article_id>.task.json. Đưa packet
này cho agent của bạn (prompt tự viết từ schemas/agent-instructions-v1.md), nhận
agent-output-v1 rồi nạp lại bằng scripts/agent_ingest.py.

Usage:
    python scripts/agent_export.py            # tối đa 20 việc
    python scripts/agent_export.py 100        # tối đa 100 việc
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.runner import AgentRunner
from src.core.config import load_settings
from src.db.store import ArticleStore


def main(argv: list[str]) -> int:
    limit = int(argv[0]) if argv else 20
    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    runner = AgentRunner(ArticleStore(db_path=db_path))
    exported = runner.export_tasks(limit=limit)
    print(f"exported={len(exported)} → data/agent_tasks/")
    for e in exported[:10]:
        print(f"  {e['article_id']}  ->  {e['path']}")
    if len(exported) > 10:
        print(f"  ... (+{len(exported) - 10} more)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
