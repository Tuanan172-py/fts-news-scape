"""
Centralized logging — loguru, 1 sink file xoay vòng + stderr.

Gọi setup_logging() đúng 1 lần tại entry point; mọi module khác chỉ
`from loguru import logger` và dùng trực tiếp.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_configured = False


def setup_logging(level: str = "INFO", log_dir: str = "logs"):
    """Cấu hình loguru: stderr + logs/monocle.log (rotation 50MB, giữ 14 ngày)."""
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
        enqueue=True,   # thread-safe: scraper + writer thread cùng ghi
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {name}:{function}:{line} | {message}",
    )
    _configured = True
    return logger
