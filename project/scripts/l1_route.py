"""
l1_route.py — TẦNG DETERMINISTIC của lớp L1 (code-first) + phát task-packet handoff.

Với mỗi work-package (hoặc silver): chạy code-first (khớp mã+alias) → lưu vào DB
(l1_tasks) → phát task-packet cho agent tra soát (data/agent_tasks/l1/<id>.task.json).

Đây là phần CODE làm hết; việc còn lại là cron kích hoạt agent xử lý các packet,
rồi nạp kết quả bằng scripts/l1_ingest.py.

Nguồn (ưu tiên work_packages — output pipeline; fallback silver):
  python scripts/l1_route.py
  python scripts/l1_route.py --source data/work_packages --review all
  python scripts/l1_route.py --review missed          # chỉ phát packet tin code không khớp
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.l1_runner import L1Runner              # noqa: E402
from src.core.config import load_settings             # noqa: E402
from src.core.stdio import force_utf8_stdio           # noqa: E402
from src.db.store import ArticleStore                 # noqa: E402

force_utf8_stdio()


def _iter_sources(source: str, reverse: bool = True):
    pats = [os.path.join(source, "*", "*", "*.json")]
    files = sorted((f for p in pats for f in glob.glob(p)), reverse=reverse)
    if not files and source != "data/silver":
        files = sorted(glob.glob(os.path.join("data/silver", "*", "*", "*.json")), reverse=reverse)
    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="data/work_packages")
    ap.add_argument("--review", choices=["all", "missed"], default="all")
    ap.add_argument("--batch-size", "-b", type=int, default=None, help="Kích thước block/lô việc cần xuất (mặc định 50)")
    ap.add_argument("--limit", "-n", type=int, default=None, help="Tối đa N việc")
    ap.add_argument("--order", choices=["desc", "asc"], default="desc", help="Thứ tự: desc (mới nhất trước), asc (cũ nhất trước)")
    ap.add_argument("--all", "-a", action="store_true", help="Xuất toàn bộ bài chưa hoàn thành")
    ap.add_argument("--no-skip-done", action="store_true", help="Không bỏ qua các bài đã có status=done")
    args = ap.parse_args(argv)

    if args.all:
        limit = None
    elif args.limit is not None:
        limit = args.limit
    elif args.batch_size is not None:
        limit = args.batch_size
    else:
        limit = 50

    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    store = ArticleStore(db_path=db_path)
    runner = L1Runner(store)

    done_aids: set[str] = set()
    if not args.no_skip_done:
        conn = store.connect()
        try:
            rows = conn.execute("SELECT article_id FROM l1_tasks WHERE status = 'done'").fetchall()
            done_aids = {r["article_id"] for r in rows}
        finally:
            conn.close()

    n = 0
    route_ctr, rel_ctr = Counter(), Counter()
    seen: set[str] = set()
    exported_tasks: list[dict] = []
    for f in _iter_sources(args.source, reverse=(args.order == "desc")):
        if limit is not None and n >= limit:
            break
        try:
            art = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        aid = art.get("article_id")
        if not aid or aid in seen or aid in done_aids:
            continue
        seen.add(aid)
        rec = runner.route_and_export(art, review=args.review)
        n += 1
        route_ctr[rec["route"]] += 1
        rel_ctr[rec["relevance"]] += 1
        if rec.get("packet_path"):
            exported_tasks.append({
                "article_id": aid,
                "title": rec.get("title") or art.get("title", ""),
                "domain": art.get("domain", ""),
                "time": art.get("published_at") or art.get("fetch_ts") or art.get("captured_at") or "",
                "path": rec["packet_path"],
            })

    print(f"== L1 route {n} tin (review={args.review}, order={args.order}, skipped_done={len(done_aids)}) ==")
    print(f"resolved (code-first khớp): {route_ctr['resolved']}")
    print(f"needs_agent (code không khớp): {route_ctr['needs_agent']}")
    print("relevance:", dict(rel_ctr))
    print(f"packets  -> data/agent_tasks/l1/<article_id>.task.json")
    print(f"trạng thái + code-first  -> DB l1_tasks (chờ agent tra soát → l1_ingest.py)")

    if exported_tasks:
        from src.agent.manifest import create_batch_manifest, print_batch_summary_table
        manifest = create_batch_manifest(exported_tasks, runner.task_dir, batch_type="l1", order=args.order)
        print_batch_summary_table(manifest)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
