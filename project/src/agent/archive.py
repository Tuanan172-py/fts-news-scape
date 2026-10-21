"""Move completed task packets into a date-partitioned archive directory."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.core.models import VN_TZ


def archive_task_packet(article_id: str, task_dir: str | Path,
                        archive_date: str | None = None) -> Path | None:
    """Move one task.json packet into the date-partitioned archive directory.

    Args:
        article_id: Article identifier.
        task_dir: Directory that holds the active task files.
        archive_date: Archive date as 'YYYYMMDD'; None uses the current date.

    Returns:
        Path of the archived file, or None if the source file does not exist or the move failed.
    """
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


def archive_completed_tasks(article_ids, task_dir: str | Path,
                            archive_date: str | None = None) -> int:
    """Move completed task packets in bulk into the archive directory.

    Handles single-article files (<aid>.task.json) and mini-batch files
    (batch_*.task.json) once every article they contain meets the DoD.

    Args:
        article_ids: Identifiers of the articles to archive.
        task_dir: Directory that holds the active task files.
        archive_date: Archive date as 'YYYYMMDD'; None uses the current date.

    Returns:
        Number of task packets archived successfully.
    """
    cnt = 0
    task_dir = Path(task_dir)
    if not archive_date:
        archive_date = datetime.now(VN_TZ).strftime("%Y%m%d")

    target_dir = task_dir / "archive" / archive_date
    target_dir.mkdir(parents=True, exist_ok=True)

    # Move single-article task files.
    for aid in article_ids:
        if archive_task_packet(aid, task_dir, archive_date):
            cnt += 1

    # Move batch packets whose articles are all processed.
    completed_set = set(article_ids)
    import json
    for batch_file in task_dir.glob("batch_*.task.json"):
        try:
            with open(batch_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            tasks = data.get("tasks", [])
            if tasks and all(t.get("article_id") in completed_set for t in tasks):
                dest = target_dir / batch_file.name
                shutil.move(str(batch_file), str(dest))
                logger.debug("[archive] moved batch {} -> {}", batch_file.name, dest)
                cnt += 1
        except Exception as e:
            logger.warning("[archive] failed to inspect/move batch {}: {}", batch_file.name, e)

    return cnt
