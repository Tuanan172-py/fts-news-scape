"""Dọn task packet ĐÃ HOÀN TẤT, giữ nguyên packet chưa ai xử lý.

Thay cho lệnh xoá trắng cũ trong `run_daily.ps1` (`Get-ChildItem -Recurse` rồi xoá mọi
`*.task.json`), vốn quét luôn `data/agent_tasks/l1/` và có thể xoá hàng trăm packet chưa
ai chạm tới (ADR 0008 §1, `docs/OPEN-ITEMS.md` §A0-2).

Bằng chứng hoàn tất lấy từ database, không suy đoán theo tên tệp:
  - packet L1   → `l1_outputs.dod_pass = 1`
  - packet Gold → `agent_outputs.dod_pass = 1`
Packet gom lô chỉ bị xoá khi TOÀN BỘ bài bên trong đều đã hoàn tất.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.core.config import load_settings          # noqa: E402
from src.core.stdio import force_utf8_stdio        # noqa: E402
from src.db.store import ArticleStore              # noqa: E402

force_utf8_stdio()

TASK_DIR = "data/agent_tasks"


def _article_ids(packet_path: Path) -> list[str]:
    """Trích danh sách article_id mà một packet phụ trách.

    Args:
        packet_path: Đường dẫn tệp `.task.json` (đơn lẻ hoặc gom lô).

    Returns:
        Danh sách mã bài; rỗng khi không đọc được (packet hỏng).
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
    """Kiểm tra một bài đã hoàn tất ở tầng tương ứng chưa (DoD đạt)."""
    table = "l1_outputs" if is_l1 else "agent_outputs"
    row = conn.execute(
        f"SELECT 1 FROM {table} WHERE article_id=? AND dod_pass=1 LIMIT 1",
        (article_id,)).fetchone()
    return row is not None


def main(argv: list[str] | None = None) -> int:
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
            # `archive/` do chính sách retention quản (Q8), không thuộc việc dọn packet.
            if "archive" in packet.parts:
                continue
            ids = _article_ids(packet)
            if not ids:
                # Không đọc được nội dung thì KHÔNG xoá — im lặng xoá là mất dữ liệu.
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
