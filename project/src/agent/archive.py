"""
Archive and Task Lifecycle Manager - don dep va luu tru task packets sau khi Ingest thanh cong.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from loguru import logger

from src.core.models import VN_TZ


def archive_task_packet(
    article_id: str,
    task_dir: str | Path,
    archive_date: str | None = None,
) -> Path | None:
    """Di chuyen 1 file task.json tu task_dir sang task_dir/archive/date/"""
    task_dir = Path(task_dir)
    src_file = task_dir / f"{article_id}.task.json"
    if not src_file.is_file():
        return None

    if not archive_date:
        archive_date = datetime.now(VN_TZ).strftime("%Y%m%d")

    target_dir = task_dir / "archive" / archive_date
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"{article_id}.task.json"

    try:
        shutil.move(str(src_file), str(target_file))
        logger.debug("[archive] moved {} -> {}", src_file.name, target_file)
        return target_file
    except Exception as e:
        logger.warning("[archive] failed to move {}: {}", src_file.name, e)
        return None


def archive_completed_tasks(
    article_ids: list[str],
    task_dir: str | Path,
    archive_date: str | None = None,
) -> int:
    """Di chuyen danh sach cac bai viet hoan thanh sang archive."""
    cnt = 0
    if not archive_date:
        archive_date = datetime.now(VN_TZ).strftime("%Y%m%d")
    for aid in article_ids:
        if archive_task_packet(aid, task_dir, archive_date):
            cnt += 1
    return cnt
