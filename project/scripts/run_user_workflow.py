"""Thực thi luồng làm việc tích hợp cho lớp phân phối người dùng."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.stdio import force_utf8_stdio            # noqa: E402
from src.pipeline.user_workflow import run             # noqa: E402

force_utf8_stdio()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="'today' hoặc YYYY-MM-DD")
    ap.add_argument("--days", type=int)
    ap.add_argument("--users", help="lọc user (phân tách bằng phẩy); mặc định: manifest")
    ap.add_argument("--l1-dir", help="thư mục output L1 (l1-entity-output-v1) để nạp")
    ap.add_argument("--agent-dir", help="thư mục output agent (agent-output-v1) để nạp")
    ap.add_argument("--no-compile", action="store_true", help="bỏ bước compile xlsx→yaml")
    ap.add_argument("--force", action="store_true", help="ép ghi đè toàn bộ file deliverable kể cả khi không có bài mới")
    ap.add_argument("--skip-scrape", action="store_true", default=True,
                    help="(mặc định BẬT) giả định cron đã scrape — cờ giữ để tường minh")
    args = ap.parse_args(argv)

    users = [u for u in args.users.split(",")] if args.users else None
    res = run(users=users, date=args.date, days=args.days,
              do_compile=not args.no_compile, force=args.force,
              l1_outputs_dir=args.l1_dir, agent_outputs_dir=args.agent_dir)
    counts = res["counts"]
    print(f"done: enabled={res['enabled']} | {res['total']} dòng final | " + ", ".join(
        f"{u}={n}" for u, n in sorted(counts.items())) or "(0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
