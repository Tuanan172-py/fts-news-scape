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
    """Ingest L1 agent-output files through the L1 DoD gate.

    Args:
        argv: Command-line arguments, excluding the program name.

    Returns:
        0 on success, 1 when any record fails ingestion.
    """

    import argparse
    ap = argparse.ArgumentParser(description="Nạp output tra soát của agent L1")
    ap.add_argument("target", nargs="+",
                    help="một hoặc nhiều output.json, hoặc thư mục chứa outputs")
    ap.add_argument("--task-dir", default=None,
                    help=f"Thư mục task packets L1 (mặc định: {paths.agent_tasks_dir() / 'l1'})")
    args = ap.parse_args(argv)

    db_path = load_settings()["database"]["path"]
    runner = L1Runner(ArticleStore(db_path=db_path), task_dir=args.task_dir)

    if not args.target:
        ap.error("thiếu <target>")
    done = failed = 0
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
                print(f"DONE   {res.get('article_id')}")
            else:
                failed += 1
                print(f"FAILED {res.get('article_id')}: {res.get('reasons') or res.get('reason')}")

    print(f"\ningested: done={done} failed={failed}")
    # A record rejected by DoD or an unreadable file is an ingest error: return non-zero so
    # `article_run.py --finish` halts the batch instead of reporting completion.
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
