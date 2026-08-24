"""
Database Snapshot Utility (Point-in-time non-blocking read snapshot).

Cho phép tạo bản sao `monocle_review.db` hoặc `monocle_snapshot.db` từ `monocle.db`
mà KHÔNG làm lock hay gián đoạn quá trình crawl/ingest của các Agents.
Sử dụng SQLite `VACUUM INTO` (yêu cầu SQLite 3.27+) hoặc SQLite Online Backup API.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from loguru import logger

from src.core.staging import safe_atomic_write


def create_db_snapshot(
    src_db_path: str | Path = "data/monocle.db",
    dst_db_path: str | Path = "data/monocle_review.db",
    *,
    overwrite: bool = True,
) -> Path:
    """Tạo bản sao snapshot của database cho User / BI tools truy vấn.

    Args:
        src_db_path: Đường dẫn database nguồn (mặc định data/monocle.db)
        dst_db_path: Đường dẫn database đích (mặc định data/monocle_review.db)
        overwrite: Nếu file đích đã tồn tại, tự động ghi đè bản mới

    Returns:
        Path: Đường dẫn tới file snapshot đã tạo
    """
    src = Path(src_db_path).resolve()
    dst = Path(dst_db_path).resolve()

    if not src.exists():
        raise FileNotFoundError(f"Database nguồn không tồn tại: {src}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    temp_dst = dst.parent / f"{dst.stem}_tmp_{os.getpid()}{dst.suffix}"

    if temp_dst.exists():
        try:
            temp_dst.unlink()
        except Exception:
            pass

    # Kết nối nguồn bằng mode read-only để không lock writer
    src_uri = f"file:{src.as_posix()}?mode=ro"
    con = sqlite3.connect(src_uri, uri=True, timeout=30.0)
    try:
        # Sử dụng VACUUM INTO ra file tạm
        # Chuyển path sang POSIX dạng an toàn cho SQL string literal
        escaped_temp = temp_dst.as_posix().replace("'", "''")
        con.execute(f"VACUUM INTO '{escaped_temp}'")
    except Exception as e:
        logger.warning(f"VACUUM INTO thất bại ({e}), chuyển sang dùng SQLite Backup API...")
        # Fallback sang SQLite Backup API nếu SQLite không hỗ trợ VACUUM INTO
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

    # Atomic swap sang file đích
    try:
        os.replace(temp_dst, dst)
        final_path = dst
    except PermissionError:
        # Nếu user đang mở DB snapshot trong DB Browser, fallback sang file có PID/timestamp
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
