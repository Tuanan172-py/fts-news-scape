"""Delete completed task packets and keep every packet nobody has processed.
"""

# Replaces the former blanket delete in `run_daily.ps1` (`Get-ChildItem -Recurse` removing
# every `*.task.json`), which also swept `data/agent_tasks/l1/` and could delete hundreds
# of untouched packets (ADR 0008 section 1, `docs/OPEN-ITEMS.md` A0-2).
#
# Completion evidence comes from the database, never from file names:
#   - L1 packet: `l1_outputs.dod_pass = 1` and not a code-first record
#   - Gold packet: `agent_outputs.dod_pass = 1`
# A batched packet is deleted only when ALL articles inside it are complete.

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.agent.article_contract import analyzed_l1_sql  # noqa: E402
from src.core import paths                         # noqa: E402
from src.core.config import load_settings          # noqa: E402
from src.core.stdio import force_utf8_stdio        # noqa: E402
from src.db.store import ArticleStore              # noqa: E402

force_utf8_stdio()

TASK_DIR = str(paths.agent_tasks_dir())


def _article_ids(packet_path: Path) -> list[str]:
    """Extract the article ids a packet is responsible for.

    Args:
        packet_path: Path of the `.task.json` file (single or batched).

    Returns:
        List of article ids; empty when the packet is unreadable (corrupt).
    """
    try:
        data = json.loads(packet_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    tasks = data.get("tasks") if isinstance(data, dict) else data
    if isinstance(tasks, list) and tasks:
        return [t.get("article_id", "") for t in tasks if isinstance(t, dict)]
    if isinstance(data, dict):
        aid = data.get("article_id") or (data.get("input") or {}).get("article_id")
        if aid:
            return [aid]
    return []


def _is_done(conn, article_id: str, is_l1: bool) -> bool:
    """Check whether an article is complete at the matching layer.

    A code-first record does not count as complete, so the packet of an article that has
    only that record is kept.

    Args:
        conn: SQLite connection.
        article_id: Article id.
        is_l1: True to check the entity-detection layer (`l1_outputs`), False for `agent_outputs`.

    Returns:
        True when the article has a passing record at the matching layer.
    """
    if is_l1:
        table, cond = "l1_outputs", analyzed_l1_sql()
    else:
        table, cond = "agent_outputs", "dod_pass = 1"
    row = conn.execute(
        f"SELECT 1 FROM {table} WHERE article_id=? AND {cond} LIMIT 1",
        (article_id,)).fetchone()
    return row is not None


def main(argv: list[str] | None = None) -> int:
    """Delete completed task packets, or list them in dry-run mode.

    Args:
        argv: Command-line arguments; defaults to `sys.argv[1:]`.

    Returns:
        Process exit code, always 0.
    """
    p = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    p.add_argument("--task-dir", default=TASK_DIR)
    p.add_argument("--db-path", default=None)
    p.add_argument("--apply", action="store_true",
                   help="thực sự xoá; mặc định chỉ liệt kê (an toàn theo mặc định)")
    args = p.parse_args(argv)

    store = ArticleStore(args.db_path or load_settings()["database"]["path"])
    conn = store.connect()
    root = Path(args.task_dir)
    deletable: list[Path] = []
    kept = 0
    unreadable = 0

    try:
        for packet in sorted(root.rglob("*.task.json")):
            # `archive/` is governed by the retention policy (Q8), not by packet cleanup.
            if "archive" in packet.parts:
                continue
            ids = _article_ids(packet)
            if not ids:
                # Unreadable content is never deleted: a silent delete loses data.
                unreadable += 1
                kept += 1
                continue
            is_l1 = "l1" in packet.parent.name.lower()
            if all(_is_done(conn, aid, is_l1) for aid in ids if aid):
                deletable.append(packet)
            else:
                kept += 1
    finally:
        conn.close()

    print(f"clean_completed_packets [{'APPLY' if args.apply else 'DRY-RUN'}]: "
          f"đã hoàn tất={len(deletable)} giữ lại={kept} không đọc được={unreadable}")
    for packet in deletable:
        print(f"  {'xoá' if args.apply else 'sẽ xoá'}: {packet}")
        if args.apply:
            try:
                packet.unlink()
            except OSError as e:
                print(f"    ! không xoá được: {e}")
    if kept:
        print(f"  ⚠️  {kept} packet CHƯA hoàn tất được giữ nguyên — không xoá.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
