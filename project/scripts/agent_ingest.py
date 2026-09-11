"""Tiếp nhận và kiểm định kết quả phân tích chuyên sâu của agent."""

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
        print("usage: agent_ingest.py <output.json | dir> [--no-archive] [--task-dir DIR]")
        return 2

    import argparse
    ap = argparse.ArgumentParser(description="Nạp agent-output-v1 do agent NGOÀI sinh ra")
    ap.add_argument("target", help="output.json hoặc thư mục chứa outputs")
    ap.add_argument("--task-dir", default="data/agent_tasks", help="Thư mục task packets (mặc định: data/agent_tasks)")
    ap.add_argument("--no-archive", action="store_true", help="Không tự động archive task packet khi DoD pass")
    args = ap.parse_args(argv)

    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    runner = AgentRunner(ArticleStore(db_path=db_path), task_dir=args.task_dir)
    done = failed = 0
    done_aids: list[str] = []
    from src.agent.batch_handoff import unpack_batch_output

    def _record(res: dict) -> None:
        """Cộng sổ 1 kết quả ingest. MỌI record đều đi qua runner.ingest_output (không bypass DoD)."""
        nonlocal done, failed
        if res.get("dod_pass"):
            done += 1
            if res.get("article_id"):
                done_aids.append(res["article_id"])
            print(f"DONE   {res['article_id']}")
        else:
            failed += 1
            print(
                f"FAILED {res.get('article_id')}: {res.get('reasons') or res.get('reason')}"
            )

    for path in _iter_paths(args.target):
        # unpack_batch_output đã bao cả 3 dạng: list, {outputs|results: [...]}, và object đơn lẻ.
        unpacked_items = unpack_batch_output(path)
        if not unpacked_items:
            failed += 1
            print(f"FAILED {path}: không đọc được agent-output (thiếu article_id)")
            continue
        for item in unpacked_items:
            _record(runner.ingest_output(item))

    if done_aids and not args.no_archive:
        from src.agent.archive import archive_completed_tasks
        archived_cnt = archive_completed_tasks(done_aids, args.task_dir)
        print(f"📦 archived: {archived_cnt}/{len(done_aids)} task packets → {args.task_dir}/archive/")

    print(f"\ningested: done={done} failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
