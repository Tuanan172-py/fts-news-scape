"""
Xuất task-packet cho agent NGOÀI (Vòng 3 infra, không LLM).

Claim work_items pending → ghi data/agent_tasks/<article_id>.task.json. Phát hành packet cho agents thực thi (prompt tự viết từ schemas/agent-instructions-v1.md), nhận
agent-output-v1 rồi nạp lại bằng scripts/agent_ingest.py.

Usage:
    python scripts/agent_export.py            # tối đa 20 việc
    python scripts/agent_export.py 100        # tối đa 100 việc
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.runner import AgentRunner
from src.core.config import load_settings
from src.core.stdio import force_utf8_stdio
from src.db.store import ArticleStore

force_utf8_stdio()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Xuất task-packet cho agent NGOÀI")
    ap.add_argument("limit_pos", nargs="?", type=int, help="Số lượng việc cần xuất (tùy chọn)")
    ap.add_argument("--batch-size", "-b", type=int, default=None, help="Kích thước block/lô việc cần xuất (mặc định 50)")
    ap.add_argument("--limit", "-n", type=int, help="Tối đa N việc")
    ap.add_argument("--order", choices=["desc", "asc"], default="desc", help="Thứ tự bốc việc: desc (mới nhất trước), asc (cũ nhất trước)")
    ap.add_argument("--all", "-a", action="store_true", help="Xuất toàn bộ việc pending")
    ap.add_argument("--sync", action="store_true", default=True, help="Tự động đồng bộ Silver nếu có Bronze mới (mặc định bật)")
    ap.add_argument("--no-sync", action="store_false", dest="sync", help="Bỏ qua bước đồng bộ Silver")
    ap.add_argument("--mini-batch", "-m", type=int, default=None, help="Gom lô thành các mini-batch packets (vd: 5 hoặc 10 bài/packet)")
    args = ap.parse_args(argv)

    if args.all:
        limit = 100000
    elif args.limit is not None:
        limit = args.limit
    elif args.batch_size is not None:
        limit = args.batch_size
    elif args.limit_pos is not None:
        limit = args.limit_pos
    else:
        limit = 50

    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    store = ArticleStore(db_path=db_path)
    if args.sync:
        from src.pipeline.derive import rederive_incremental
        rederive_incremental(store)
    runner = AgentRunner(store)
    exported = runner.export_tasks(limit=limit, order=args.order)
    print(f"exported={len(exported)} → data/agent_tasks/")
    if exported:
        from src.agent.manifest import create_batch_manifest, print_batch_summary_table
        manifest = create_batch_manifest(exported, runner.task_dir, batch_type="gold", order=args.order)
        print_batch_summary_table(manifest)
        if args.mini_batch and args.mini_batch > 0:
            from src.agent.batch_handoff import split_tasks_into_batches
            batches = split_tasks_into_batches(exported, batch_size=args.mini_batch, base_dir=runner.task_dir)
            print(f"📦 Đã đóng gói {len(batches)} mini-batch packets (size={args.mini_batch}) → {runner.task_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
