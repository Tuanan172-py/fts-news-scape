"""Operate the production news lakehouse on FRA - Data/news: publish, verify, status; run with cwd = project/."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.stdio import force_utf8_stdio  # noqa: E402
from src.research_db import master, production  # noqa: E402

force_utf8_stdio()


def _dump(obj: object) -> None:
    """Print an object as indented JSON.

    Args:
        obj: JSON-serialisable object.
    """
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def main(argv: list[str]) -> int:
    """Run one subcommand.

    Args:
        argv: Command-line arguments without the program name.

    Returns:
        0 on success, 1 on failure.
    """
    ap = argparse.ArgumentParser(description="Production tin tức Research (FRA - Data/news).")
    ap.add_argument("--target", help=f"thư mục news dùng thay {production.TARGET_ENV}")
    ap.add_argument("--ops-db", help="DB vận hành (mặc định resolve_db_path())")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("publish", help="chạy cổng kiểm nghiệm rồi ghi các phân vùng ngày thay đổi")
    p.add_argument("--dry-run", action="store_true", help="chỉ chạy cổng, không ghi gì")
    p.add_argument("--rebuild", action="store_true", help="ghi lại mọi ngày (lần đầu hoặc sau sự cố)")
    sub.add_parser("verify", help="băm lại mọi phân vùng, đối chiếu chỉ mục và manifest")
    sub.add_parser("status", help="trạng thái master cục bộ và manifest production")
    args = ap.parse_args(argv)

    if args.cmd == "publish":
        if args.ops_db:
            ops_db = Path(args.ops_db)
        else:
            from src.core.config import resolve_db_path
            ops_db = Path(resolve_db_path())
        out = production.publish(ops_db, target=args.target, reason="manual",
                                 dry_run=args.dry_run, rebuild=args.rebuild)
        d = out.to_dict()
        d["written"] = f"{len(out.written)} phân vùng" + (f", ví dụ {out.written[:3]}" if out.written else "")
        _dump(d)
        return 0 if out.status in ("published", "unchanged", "dry_run") and not out.failed else 1
    if args.cmd == "verify":
        try:
            res = production.verify(args.target)
        except production.PublishError as exc:
            print(exc)
            return 1
        _dump(res)
        return 0 if res["ok"] else 1
    conn = master.open_master()
    try:
        _dump({"meta": dict(conn.execute("SELECT key, value FROM _meta").fetchall()),
               "articles": conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0],
               "rejected_held": conn.execute("SELECT COUNT(*) FROM _rejects").fetchone()[0],
               "partitions": conn.execute("SELECT COUNT(*) FROM _partitions").fetchone()[0],
               "dirty_days": master.dirty_days(conn)})
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
