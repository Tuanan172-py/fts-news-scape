"""Manage the staging area and perform atomic, safe file writes."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Any

from loguru import logger

from src.core import paths
from src.core.models import VN_TZ


def ensure_staging_dir(base_dir: str | Path | None = None) -> Path:
    """Create the staging directory if it does not exist.

    Args:
        base_dir: Staging directory to create. Defaults to `paths.staging_dir()`.

    Returns:
        Path of the staging directory.
    """
    p = paths.resolve_data_path(base_dir) if base_dir else paths.staging_dir()
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
    """Write data to disk safely through a staging file and an atomic replace.

    Args:
        target_path: Destination file path.
        writer_fn_or_content: Content (str/bytes) or a callable that receives the file handle and writes to it (for example json.dump or csv.writer).
        fallback_on_lock: If True, a PermissionError on Windows writes a new versioned file (stem_HHMMSS.ext) instead of raising.
        encoding: Encoding for text mode.
        binary: True to write a binary file.
        staging_dir: Optional staging directory. Defaults to the destination directory.

    Returns:
        Tuple of the path actually written and a flag that is True when a fallback version was written because the file was locked.

    Raises:
        TypeError: If the content type does not match the write mode.
        PermissionError: If the destination is locked and `fallback_on_lock` is False, or the fallback write also fails.
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

        # If the destination exists and its bytes are identical to tmp_path, skip os.replace
        # to avoid triggering a Windows lock or a OneDrive file-sync conflict.
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

        # Try an atomic swap onto the destination file.
        try:
            os.replace(tmp_path, dst)
            return dst, False
        except PermissionError as e:
            if not fallback_on_lock:
                raise
            # Windows lock fallback: write a timestamped copy so the pipeline does not crash.
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
    """Write JSON data safely through the staging area with an atomic replace.

    Args:
        data: Data structure to serialize to JSON.
        target_path: Destination file path.
        indent: JSON indentation width.
        fallback_on_lock: If True, write a fallback file when the destination is locked on Windows.
        staging_dir: Optional staging directory.

    Returns:
        Tuple of the path actually written and a flag that is True for a fallback file.
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
    staging_dir: str | Path | None = None,
    max_age_seconds: int = 86400,
) -> int:
    """Delete leftover .tmp files in the staging directory that exceed the maximum age.

    Args:
        staging_dir: Staging directory to clean. Defaults to `paths.staging_dir()`.
        max_age_seconds: Maximum file age in seconds before deletion.

    Returns:
        Number of temporary files deleted.
    """
    p = Path(staging_dir) if staging_dir else paths.staging_dir()
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
