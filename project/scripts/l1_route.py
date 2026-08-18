"""
l1_route.py — Chạy quy trình L1 2 tầng trên kho silver.

  Tầng 1 (code-first): khớp mã+alias. Khớp được → ghi 'resolved'.
  Tầng 2 (handoff)   : không khớp → build task-packet cho agent L1.

Đầu ra:
  - data/agent_tasks/l1/resolved.jsonl        (tin code-first đã nhận diện, tag thẳng)
  - data/agent_tasks/l1/<article_id>.task.json (mỗi tin cần agent nhận diện)
  - in bảng tóm tắt split resolved/needs_agent.

Chạy:
  python scripts/l1_route.py
  python scripts/l1_route.py --silver data/silver --out data/agent_tasks/l1
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.entities import load_registry            # noqa: E402
from src.agent.l1_router import (                        # noqa: E402
    build_l1_task_packet, route_article, write_l1_packet,
)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--silver", default="data/silver")
    ap.add_argument("--out", default="data/agent_tasks/l1")
    args = ap.parse_args(argv)

    reg = load_registry()
    os.makedirs(args.out, exist_ok=True)
    resolved_path = os.path.join(args.out, "resolved.jsonl")

    n = 0
    route_ctr, rel_ctr = Counter(), Counter()
    seen: set[str] = set()

    with open(resolved_path, "w", encoding="utf-8") as fres:
        for f in glob.glob(os.path.join(args.silver, "*", "*", "*.json")):
            try:
                art = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            aid = art.get("article_id")
            if aid in seen:
                continue
            seen.add(aid)
            rec = route_article(art, reg)
            n += 1
            route_ctr[rec["route"]] += 1
            rel_ctr[rec["relevance"]] += 1
            if rec["route"] == "resolved":
                fres.write(json.dumps(rec, ensure_ascii=False) + "\n")
            else:
                pkt = build_l1_task_packet(art, rec)
                write_l1_packet(pkt, args.out)

    print(f"== L1 route {n} tin ==")
    print(f"resolved (code-first): {route_ctr['resolved']}  -> {resolved_path}")
    print(f"needs_agent (handoff): {route_ctr['needs_agent']}  -> {args.out}/<id>.task.json")
    print("relevance:", dict(rel_ctr))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
