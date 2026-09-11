"""Quản lý vùng đệm staging và thực thi ghi tệp an toàn (Atomic Safe I/O)."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Any

from loguru import logger

from src.core.models import VN_TZ

DEFAULT_STAGING_DIR = "data/staging"


def ensure_staging_dir(base_dir: str | Path = DEFAULT_STAGING_DIR) -> Path:
    """Tạo thư mục staging nếu chưa tồn tại.

    Args:
        base_dir: Đường dẫn thư mục staging cần tạo.

    Returns:
        Đối tượng Path của thư mục staging.
    """
    p = Path(base_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_atomic_write(
    target_path: str | Path,
    writer_fn_or_content: str | bytes | Callable[[Any], None],
    *,
    fallback_on_lock: bool = True,
    encoding: str = "utf-8",
    binary: bool = False,
    staging_dir: str | Path | None = None,
) -> tuple[Path, bool]:
    """Ghi dữ liệu an toàn ra đĩa qua file staging + atomic replace.

    Args:
        target_path: Đường dẫn file đích cần ghi.
        writer_fn_or_content: Nội dung (str/bytes) hoặc hàm nhận file handle để ghi (vd: json.dump, csv.writer).
        fallback_on_lock: Nếu True và gặp PermissionError trên Windows, sinh file version mới (stem_HHMMSS.ext) thay vì raise.
        encoding: Encoding cho text mode (mặc định utf-8).
        binary: True nếu ghi file nhị phân.
        staging_dir: Thư mục staging tùy chọn (mặc định data/staging hoặc cùng thư mục đích).

    Returns:
        tuple[Path, bool]: (Đường dẫn file thực tế đã ghi, True nếu là fallback version do bị lock)
    """
    dst = Path(target_path).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    if staging_dir:
        stg_dir = Path(staging_dir).resolve()
        stg_dir.mkdir(parents=True, exist_ok=True)
        unique_id = f"{os.getpid()}_{uuid.uuid4().hex[:8]}"
        tmp_path = stg_dir / f"{dst.stem}_{unique_id}{dst.suffix}.tmp"
    else:
        unique_id = f"{os.getpid()}_{uuid.uuid4().hex[:8]}"
        tmp_path = dst.parent / f"{dst.stem}_{unique_id}{dst.suffix}.tmp"

    mode = "wb" if binary else "w"
    open_kwargs = {} if binary else {"encoding": encoding, "newline": ""}

    try:
        with open(tmp_path, mode, **open_kwargs) as f:
            if callable(writer_fn_or_content):
                writer_fn_or_content(f)
            elif binary and isinstance(writer_fn_or_content, bytes):
                f.write(writer_fn_or_content)
            elif not binary and isinstance(writer_fn_or_content, str):
                f.write(writer_fn_or_content)
            else:
                raise TypeError(f"Unsupported content type: {type(writer_fn_or_content)}")

        # Kiểm tra nội dung: Nếu file đích đã tồn tại và nội dung bytes giống hệt tmp_path,
        # bỏ qua bước os.replace để không kích hoạt Windows lock & OneDrive file-sync conflict.
        if dst.exists():
            try:
                if tmp_path.stat().st_size == dst.stat().st_size:
                    import hashlib
                    h_tmp = hashlib.sha256(tmp_path.read_bytes()).digest()
                    h_dst = hashlib.sha256(dst.read_bytes()).digest()
                    if h_tmp == h_dst:
                        return dst, False
            except Exception:
                pass

        # Cố gắng atomic swap vào file đích
        try:
            os.replace(tmp_path, dst)
            return dst, False
        except PermissionError as e:
            if not fallback_on_lock:
                raise
            # Windows lock fallback: Tạo file backup có timestamp để không làm crash pipeline
            ts = datetime.now(VN_TZ).strftime("%H%M%S")
            fallback_dst = dst.parent / f"{dst.stem}_{ts}{dst.suffix}"
            try:
                os.replace(tmp_path, fallback_dst)
                logger.warning(
                    f"File '{dst.name}' đang bị khóa bởi process khác (Excel/User). "
                    f"Đã lưu bản snapshot vào '{fallback_dst.name}'."
                )
                return fallback_dst, True
            except Exception as fe:
                logger.error(f"Fallback save failed for '{fallback_dst}': {fe}")
                raise e
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


def safe_json_dump(
    data: Any,
    target_path: str | Path,
    *,
    indent: int = 2,
    fallback_on_lock: bool = True,
    staging_dir: str | Path | None = None,
) -> tuple[Path, bool]:
    """Ghi dữ liệu JSON an toàn qua vùng đệm staging và thay thế nguyên tử.

    Args:
        data: Cấu trúc dữ liệu cần tuần tự hóa sang JSON.
        target_path: Đường dẫn tệp đích cần ghi.
        indent: Độ thụt lề định dạng JSON.
        fallback_on_lock: Cờ cho phép lưu tệp dự phòng nếu tệp đích bị khóa trên Windows.
        staging_dir: Đường dẫn thư mục staging tùy chọn.

    Returns:
        Bộ (Path, bool) gồm đường dẫn tệp thực tế và cờ báo tệp dự phòng.
    """
    def _write(f):
        json.dump(data, f, ensure_ascii=False, indent=indent)

    return safe_atomic_write(
        target_path,
        _write,
        fallback_on_lock=fallback_on_lock,
        encoding="utf-8",
        staging_dir=staging_dir,
    )


def clean_stale_staging(
    staging_dir: str | Path = DEFAULT_STAGING_DIR,
    max_age_seconds: int = 86400,
) -> int:
    """Dọn dẹp các tệp tạm .tmp tồn đọng trong thư mục staging vượt quá thời gian tối đa.

    Args:
        staging_dir: Đường dẫn thư mục staging cần dọn dẹp.
        max_age_seconds: Tuổi thọ tối đa của tệp tính bằng giây trước khi xóa.

    Returns:
        Số lượng tệp tạm đã được xóa bỏ thành công.
    """
    p = Path(staging_dir)
    if not p.exists():
        return 0
    now = time.time()
    cleaned = 0
    for f in p.glob("*.tmp"):
        try:
            if now - f.stat().st_mtime > max_age_seconds:
                f.unlink()
                cleaned += 1
        except Exception:
            pass
    return cleaned
