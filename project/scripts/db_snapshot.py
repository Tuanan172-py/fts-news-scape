"""Create a point-in-time snapshot of the SQLite database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core import paths
from src.core.config import load_settings
from src.core.stdio import force_utf8_stdio
from src.db.snapshot import create_db_snapshot

force_utf8_stdio()


def main(argv: list[str]) -> int:
    """Create a snapshot of the operational database.

    Args:
        argv: Command-line arguments, excluding the program name.

    Returns:
        0 on success, 1 when the snapshot fails.
    """
    p = argparse.ArgumentParser(description="Tạo snapshot SQLite DB an toàn (Point-in-time)")
    p.add_argument("--src", help="Database nguồn (mặc định DB vận hành theo settings)")
    p.add_argument("--out", "-o", default=str(paths.snapshots_dir() / "monocle_review.db"),
                   help="File snapshot đích")
    p.add_argument("--check", action="store_true",
                   help="Kiểm tra tính toàn vẹn và sẵn sàng đóng gói của snapshot")
    args = p.parse_args(argv)

    db_path = args.src or load_settings()["database"]["path"]
    target_out = Path(args.out).resolve()

    if args.check:
        if not target_out.exists():
            print(f"Snapshot chưa tồn tại tại {target_out}, đang tạo mới...")
            try:
                target_out = create_db_snapshot(src_db_path=db_path, dst_db_path=args.out)
            except Exception as e:
                print(f"[!] Lỗi khi tạo snapshot: {e}", file=sys.stderr)
                return 1

        try:
            import sqlite3
            uri = f"file:{target_out.as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=30.0)
            try:
                integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
                table_count = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
                art_count = conn.execute("SELECT count(*) FROM articles").fetchone()[0]
            finally:
                conn.close()

            size_mb = target_out.stat().st_size / (1024 * 1024)
            print("=== SNAPSHOT AUDIT & SHAREPOINT READINESS ===")
            print(f"  Snapshot file       : {target_out}")
            print(f"  Size                : {size_mb:.2f} MB")
            print(f"  Table count         : {table_count}")
            print(f"  Articles count      : {art_count:,}")
            print(f"  PRAGMA integrity    : {integrity}")

            if integrity == "ok":
                print("\nVERDICT: SNAPSHOT READY FOR SHAREPOINT PACKAGING (100% OK)")
                return 0
            print(f"\nVERDICT: SNAPSHOT INTEGRITY ERROR: {integrity}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"[!] Lỗi khi kiểm tra snapshot: {e}", file=sys.stderr)
            return 1

    try:
        out_path = create_db_snapshot(src_db_path=db_path, dst_db_path=args.out)
        print(f">>> Snapshot đã tạo thành công tại: {out_path.resolve()}")
        print("    Bạn có thể mở file này bằng DB Browser for SQLite mà không lo làm nghẽn Agents.")
        return 0
    except Exception as e:
        print(f"[!] Lỗi khi tạo snapshot: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

