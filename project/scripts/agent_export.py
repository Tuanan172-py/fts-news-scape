"""
Xuất task-packet cho agent NGOÀI (Vòng 3 infra, không LLM).

Claim work_items pending (mặc định CHỈ bài đã qua L1) → ghi data/agent_tasks/<article_id>.task.json. Phát hành packet cho agents thực thi (prompt tự viết từ schemas/agent-instructions-v1.md), nhận
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
    ap.add_argument("--require-l1", action="store_true", default=True, help="Chỉ bốc bài đã có l1_outputs.dod_pass=1 (mặc định BẬT)")
    ap.add_argument("--no-require-l1", action="store_false", dest="require_l1", help="Bốc cả bài chưa có L1 (rút backlog cũ; packet sẽ thiếu l1_entities)")
    ap.add_argument("--subscriber-only", action="store_true", default=True, help="Chỉ bốc bài có người dùng active theo dõi (mặc định BẬT)")
    ap.add_argument("--no-subscriber-only", action="store_false", dest="subscriber_only", help="Bốc cả bài không có người dùng active theo dõi")
    ap.add_argument("--user", "-u", action="append", help="Lọc bài theo người dùng cụ thể (vd: --user AnPT, hoặc dùng nhiều lần)")
    ap.add_argument("--days", "-d", type=int, default=None, help="Chỉ bốc bài trong N ngày gần nhất (tính từ ngày bài viết)")
    ap.add_argument("--date", default=None, help="Chỉ bốc bài trong ngày cụ thể (YYYY-MM-DD, today, all)")
    ap.add_argument("--dry-run", action="store_true", help="Chỉ kiểm tra và đếm số bài thỏa điều kiện, không claim và không ghi file")
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

    # Xử lý tham số user (hỗ trợ phân tách dấu phẩy hoặc lặp cờ)
    user_filter = None
    if args.user:
        user_filter = []
        for u in args.user:
            for item in u.split(","):
                item_clean = item.strip()
                if item_clean:
                    user_filter.append(item_clean)

    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    store = ArticleStore(db_path=db_path)
    if args.sync:
        from src.pipeline.derive import rederive_incremental
        rederive_incremental(store)
    runner = AgentRunner(store)
    exported = runner.export_tasks(
        limit=limit, order=args.order, require_l1=args.require_l1,
        subscriber_only=args.subscriber_only,
        user=user_filter,
        date=args.date,
        days=args.days,
        dry_run=args.dry_run,
    )

    filter_details = []
    if user_filter:
        filter_details.append(f"user={user_filter}")
    if args.date:
        filter_details.append(f"date={args.date}")
    if args.days:
        filter_details.append(f"days={args.days}")
    filter_str = f" ({', '.join(filter_details)})" if filter_details else ""
    print(f"exported={len(exported)} → data/agent_tasks/ (require_l1={args.require_l1}, subscriber_only={args.subscriber_only}){filter_str}")

    if not exported and args.require_l1:
        print("Không có việc nào đã qua L1. Chạy scripts/l1_route.py + l1_ingest.py trước, "
              "hoặc dùng --no-require-l1 để rút backlog cũ.")
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
