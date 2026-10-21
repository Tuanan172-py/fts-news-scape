"""Ingest and validate the L1 entity recognition results."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.l1_runner import L1Runner
from src.core import paths
from src.core.config import load_settings
from src.core.stdio import force_utf8_stdio
from src.db.store import ArticleStore

force_utf8_stdio()


def _iter_paths(arg: str):
    """Yield the output JSON files designated by a path argument.

    Args:
        arg: Path to a single output file or to a directory of `*.json` files.

    Yields:
        Each output file path, sorted by name when `arg` is a directory.
    """
    p = Path(arg)
    if p.is_dir():
        yield from sorted(p.glob("*.json"))
    else:
        yield p


def main(argv: list[str]) -> int:
    """Ingest L1 agent-output files, or drain the code-first queue.

    Args:
        argv: Command-line arguments, excluding the program name.

    Returns:
        0 on success, 1 when any record fails ingestion.
    """

    import argparse
    ap = argparse.ArgumentParser(description="Nạp output tra soát của agent L1")
    ap.add_argument("target", nargs="*",
                    help="một hoặc nhiều output.json, hoặc thư mục chứa outputs")
    ap.add_argument("--task-dir", default=None,
                    help=f"Thư mục task packets L1 (mặc định: {paths.agent_tasks_dir() / 'l1'})")
    ap.add_argument("--no-archive", action="store_true", help="Không tự động archive task packet khi DoD pass")
    ap.add_argument("--code-first", action="store_true",
                    help="Vật chất hoá l1_tasks route=resolved (tra danh mục tất định) → l1_outputs")
    ap.add_argument("--limit", type=int, default=None, help="Giới hạn số task khi --code-first")
    ap.add_argument("--dry-run", action="store_true", help="Chỉ đếm, không ghi DB")
    args = ap.parse_args(argv)

    db_path = load_settings()["database"]["path"]
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

    for path in (p for t in args.target for p in _iter_paths(t)):
        # unpack_batch_output handles all three shapes: array, {outputs|results: [...]}, single object.
        # Without it, an agent that returns a whole batch in one file would break ingestion silently.
        items = unpack_batch_output(path)
        if not items:
            # A valid empty-array file (all rows moved to a newer patch batch) is
            # skipped silently: having nothing to ingest is not an ingest error.
            try:
                empty_ok = json.loads(Path(path).read_text(encoding="utf-8")) == []
            except (OSError, ValueError):
                empty_ok = False
            if empty_ok:
                print(f"SKIP   {path}: tệp rỗng sau khi dồn hàng sang lô mới")
                continue
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
        task_dir = args.task_dir or (paths.agent_tasks_dir() / "l1")
        archived_cnt = archive_completed_tasks(done_aids, task_dir)
        print(f"📦 archived: {archived_cnt}/{len(done_aids)} L1 task packets → {task_dir}/archive/")

        # Remove completed batch files automatically when every task in the batch has passed.
        task_dir_path = Path(task_dir)
        done_set = set(done_aids)
        for b_file in task_dir_path.glob("l1_batch_*.task.json"):
            try:
                b_data = json.loads(b_file.read_text(encoding="utf-8"))
                b_tasks = b_data.get("tasks", [])
                if b_tasks and all(t.get("article_id") in done_set or runner.store.get_l1_output(t.get("article_id")) for t in b_tasks):
                    b_file.unlink()
                    print(f"🧹 Tu dong don file batch task hoan tat: {b_file.name}")
            except (OSError, json.JSONDecodeError) as e:
                print(f"⚠️ Khong the doc hoac don file batch {b_file.name}: {e}", file=sys.stderr)

    print(f"\ningested: done={done} failed={failed}")
    # A record rejected by DoD or an unreadable file is an ingest error: return non-zero so
    # `article_run.py --finish` halts the batch instead of reporting completion.
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
