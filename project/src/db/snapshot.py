"""Create database snapshot copies without locking the main database."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from loguru import logger

from src.core import paths
from src.core.staging import safe_atomic_write


def create_db_snapshot(
    src_db_path: str | Path | None = None,
    dst_db_path: str | Path | None = None,
    *,
    overwrite: bool = True,
) -> Path:
    """Create a snapshot copy of the database for lookup and testing.

    Args:
        src_db_path: Source database path. Defaults to the operational DB.
        dst_db_path: Destination snapshot path. Defaults to `<root>/snapshots/monocle_review.db`.
        overwrite: If True, overwrite the destination file when it exists.

    Returns:
        Path of the snapshot file created.

    Raises:
        FileNotFoundError: If the source database file does not exist.
    """
    if src_db_path is None:
        from src.core.config import resolve_db_path
        src_db_path = resolve_db_path()
    src = Path(src_db_path).resolve()
    dst = Path(dst_db_path or paths.snapshots_dir() / "monocle_review.db").resolve()

    if not src.exists():
        raise FileNotFoundError(f"Database nguồn không tồn tại: {src}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    temp_dst = dst.parent / f"{dst.stem}_tmp_{os.getpid()}{dst.suffix}"

    if temp_dst.exists():
        try:
            temp_dst.unlink()
        except Exception:
            pass

    # Open the source read-only so the writer is not locked.
    src_uri = f"file:{src.as_posix()}?mode=ro"
    con = sqlite3.connect(src_uri, uri=True, timeout=30.0)
    try:
        # VACUUM INTO writes to a temp file; the POSIX path is escaped for use in an SQL string literal.
        escaped_temp = temp_dst.as_posix().replace("'", "''")
        con.execute(f"VACUUM INTO '{escaped_temp}'")
    except Exception as e:
        logger.warning(f"VACUUM INTO thất bại ({e}), chuyển sang dùng SQLite Backup API...")
        # Fall back to the SQLite Backup API when VACUUM INTO is unsupported.
        dst_conn = sqlite3.connect(temp_dst)
        try:
            src_conn = sqlite3.connect(src_uri, uri=True, timeout=30.0)
            with dst_conn:
                src_conn.backup(dst_conn)
            src_conn.close()
        finally:
            dst_conn.close()
    finally:
        con.close()

    # Swap atomically onto the destination file.
    try:
        os.replace(temp_dst, dst)
        final_path = dst
    except PermissionError:
        # If the snapshot is open in DB Browser, fall back to a timestamped file.
        from datetime import datetime
        from src.core.models import VN_TZ
        ts = datetime.now(VN_TZ).strftime("%H%M%S")
        fallback_dst = dst.parent / f"{dst.stem}_{ts}{dst.suffix}"
        os.replace(temp_dst, fallback_dst)
        logger.warning(
            f"File '{dst.name}' đang mở trong DB Browser/tool khác. "
            f"Đã lưu snapshot vào '{fallback_dst.name}'."
        )
        final_path = fallback_dst

    logger.info(f"Đã tạo DB snapshot thành công: {final_path}")
    return final_path
