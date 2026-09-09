"""
l1_ingest.py — Nạp output tra soát của agent L1 (l1-entity-output-v1).

Với mỗi file output: validate schema + check_l1_dod (grounding + checklist) →
lưu l1_outputs → set l1_tasks.status = done/failed. Idempotent theo article_id.

Chạy sau khi agent (do cron kích hoạt) xử lý các packet trong data/agent_tasks/l1/.

Che do --code-first: KHONG doc file agent, ma vat chat hoa ket qua TRA DANH MUC tat dinh
(l1_tasks route=resolved, status=pending) thanh l1-entity-output-v1 va nap thang vao
l1_outputs voi l1_source='code_first'. Xem docs/decisions/0003-code-first-l1-delivery.md.

Usage:
    python scripts/l1_ingest.py <output.json | thư_mục>
    python scripts/l1_ingest.py data/agent_outputs_l1/
    python scripts/l1_ingest.py --code-first --dry-run
    python scripts/l1_ingest.py --code-first [--limit N]
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

    import argparse
    ap = argparse.ArgumentParser(description="Nạp output tra soát của agent L1")
    ap.add_argument("target", nargs="?", help="output.json hoặc thư mục chứa outputs")
    ap.add_argument("--task-dir", default="data/agent_tasks/l1", help="Thư mục task packets L1 (mặc định: data/agent_tasks/l1)")
    ap.add_argument("--no-archive", action="store_true", help="Không tự động archive task packet khi DoD pass")
    ap.add_argument("--code-first", action="store_true",
                    help="Vật chất hoá l1_tasks route=resolved (tra danh mục tất định) → l1_outputs")
    ap.add_argument("--limit", type=int, default=None, help="Giới hạn số task khi --code-first")
    ap.add_argument("--dry-run", action="store_true", help="Chỉ đếm, không ghi DB")
    args = ap.parse_args(argv)

    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    runner = L1Runner(ArticleStore(db_path=db_path), task_dir=args.task_dir)

    if args.code_first:
        stat = runner.drain_code_first(limit=args.limit, dry_run=args.dry_run)
        tag = "DRY-RUN " if args.dry_run else ""
        print(f"{tag}code-first: quét={stat['scanned']} ghi={stat['written']} "
              f"dod_fail={stat['dod_fail']} trả-lại-agent={stat['rerouted']}")
        return 0

    if not args.target:
        ap.error("thiếu <target>, hoặc dùng --code-first")
    done = failed = 0
    done_aids: list[str] = []
    from src.agent.batch_handoff import unpack_batch_output

    for path in _iter_paths(args.target):
        # unpack_batch_output bao cả 3 dạng: mảng, {outputs|results: [...]}, object đơn lẻ.
        # Không có nó thì agent trả cả lô trong 1 file là ingest hỏng im lặng.
        items = unpack_batch_output(path)
        if not items:
            failed += 1
            print(f"FAILED {path}: không đọc được l1-entity-output (thiếu article_id)")
            continue
        for item in items:
            res = runner.ingest_output(item)
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
