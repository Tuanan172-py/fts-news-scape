"""Write the delivery report files for each user."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.entities import load_registry           # noqa: E402
from src.core.config import load_settings              # noqa: E402
from src.core.stdio import force_utf8_stdio            # noqa: E402
from src.db.store import ArticleStore                  # noqa: E402
from src.export.user_output import UserOutputWriter    # noqa: E402
from src.users.compile import DEFAULT_OUTPUT_ROOT, enabled_users            # noqa: E402

force_utf8_stdio()


def main(argv: list[str]) -> int:
    """Write per-user deliverable files, or print the output path contract.

    Args:
        argv: Command-line arguments.

    Returns:
        Exit code 0.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="'today' hoặc YYYY-MM-DD (mặc định: mọi ngày)")
    ap.add_argument("--days", type=int, help="N ngày gần nhất")
    ap.add_argument("--users", help="lọc user, phân tách bằng dấu phẩy (mặc định: manifest)")
    ap.add_argument("--force", action="store_true", help="ép ghi đè toàn bộ file deliverable kể cả khi không có bài mới")
    ap.add_argument("--where", action="store_true",
                    help="chỉ in hợp đồng đường dẫn rồi thoát, không đọc CSDL")
    args = ap.parse_args(argv)

    # The path contract needs a command that prints it; without one the orchestrator
    # probes by reading source and listing directories (the 21/09 trace spent six model
    # steps to find that this directory is at the repository root, not under `project/`).
    if args.where:
        print(f"output_root   : {DEFAULT_OUTPUT_ROOT}")
        print(f"deliverable   : {DEFAULT_OUTPUT_ROOT}/<user>/<YYYY-MM-DD>.xlsx")
        print(f"users bật     : {', '.join(sorted(enabled_users())) or '(không có)'}")
        print("lưu ý          : thư mục này ở GỐC KHO, không nằm trong project/")
        return 0

    db_path = load_settings()["database"]["path"]
    reg = load_registry()
    if args.users:
        enabled = {u.strip() for u in args.users.split(",") if u.strip()}
    else:
        enabled = enabled_users()
    writer = UserOutputWriter(ArticleStore(db_path=db_path), reg, enabled=enabled or None)
    counts = writer.write(date=args.date, days=args.days, force=args.force)
    total = sum(counts.values())
    print(f"done: {len(counts)} user, {total} dòng final. " + ", ".join(
        f"{u}={n}" for u, n in sorted(counts.items())))
    # Print the written paths so nobody has to search for them.
    print(f"output_root: {DEFAULT_OUTPUT_ROOT}")
    for user in sorted(counts):
        print(f"  {user}: {DEFAULT_OUTPUT_ROOT / user}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
