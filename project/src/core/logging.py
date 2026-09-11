"""Cấu hình hệ thống ghi log tập trung sử dụng Loguru."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_configured = False


def setup_logging(level: str = "INFO", log_dir: str = "logs"):
    """Khởi tạo cấu hình ghi log ra bảng điều khiển và tệp lưu trữ xoay vòng.

    Args:
        level: Mức độ log tối thiểu cần ghi.
        log_dir: Thư mục chứa tệp log lưu trữ.

    Returns:
        Đối tượng Logger đã được cấu hình.
    """
    global _configured
    if _configured:
        return logger

    logger.remove()
    logger.add(sys.stderr, level=level,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}")
    log_path = Path(log_dir) / "monocle.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_path,
        level=level,
        rotation="50 MB",
        retention="14 days",
        encoding="utf-8",
        enqueue=True,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {name}:{function}:{line} | {message}",
    )
    _configured = True
    return logger
