"""Configure centralized Loguru logging."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from src.core import paths

_configured = False


def setup_logging(level: str = "INFO", log_dir: str | Path | None = None):
    """Configure logging to the console and a rotating log file.

    Args:
        level: Minimum log level to record.
        log_dir: Directory for the log file. Defaults to `paths.logs_dir()`.

    Returns:
        The configured Logger.
    """
    global _configured
    if _configured:
        return logger

    logger.remove()
    logger.add(sys.stderr, level=level,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}")
    log_path = Path(log_dir or paths.logs_dir()) / "monocle.log"
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
