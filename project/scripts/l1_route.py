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


def _iter_sources(source: str):
    pats = [os.path.join(source, "*", "*", "*.json")]
    files = sorted(f for p in pats for f in glob.glob(p))
    if not files and source != "data/silver":
        files = sorted(glob.glob(os.path.join("data/silver", "*", "*", "*.json")))
    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="data/work_packages")
    ap.add_argument("--review", choices=["all", "missed"], default="all")
    args = ap.parse_args(argv)

    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    runner = L1Runner(ArticleStore(db_path=db_path))

    n = 0
    route_ctr, rel_ctr = Counter(), Counter()
    seen: set[str] = set()
    for f in _iter_sources(args.source):
        try:
            art = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        aid = art.get("article_id")
        if not aid or aid in seen:
            continue
        seen.add(aid)
        rec = runner.route_and_export(art, review=args.review)
        n += 1
        route_ctr[rec["route"]] += 1
        rel_ctr[rec["relevance"]] += 1

    print(f"== L1 route {n} tin (review={args.review}) ==")
    print(f"resolved (code-first khớp): {route_ctr['resolved']}")
    print(f"needs_agent (code không khớp): {route_ctr['needs_agent']}")
    print("relevance:", dict(rel_ctr))
    print(f"packets  -> data/agent_tasks/l1/<article_id>.task.json")
    print(f"trạng thái + code-first  -> DB l1_tasks (chờ agent tra soát → l1_ingest.py)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
