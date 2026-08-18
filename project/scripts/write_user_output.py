"""
write_user_output.py — Ghi output CSV cuối cho từng user (gate đủ 2 layer).

Chỉ ghi article có l1_outputs.dod_pass=1 AND agent_outputs.dod_pass=1, định tuyến theo
subscription. Output: users/output/<name>/<YYYY-MM-DD>/{L1,agent,final}.csv.

Usage:
    python scripts/write_user_output.py --date today
    python scripts/write_user_output.py --days 7 --users AnPT,A
"""
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
from src.users.compile import enabled_users            # noqa: E402

force_utf8_stdio()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="'today' hoặc YYYY-MM-DD (mặc định: mọi ngày)")
    ap.add_argument("--days", type=int, help="N ngày gần nhất")
    ap.add_argument("--users", help="lọc user, phân tách bằng dấu phẩy (mặc định: manifest)")
    args = ap.parse_args(argv)

    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    reg = load_registry()
    if args.users:
        enabled = {u.strip() for u in args.users.split(",") if u.strip()}
    else:
        enabled = enabled_users()
    writer = UserOutputWriter(ArticleStore(db_path=db_path), reg, enabled=enabled or None)
    counts = writer.write(date=args.date, days=args.days)
    total = sum(counts.values())
    print(f"done: {len(counts)} user, {total} dòng final. " + ", ".join(
        f"{u}={n}" for u, n in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
