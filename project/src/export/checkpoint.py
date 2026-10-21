"""Manage the export progress checkpoint of each user."""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from src.core.models import now_vn_iso
from src.core.staging import safe_atomic_write

CHECKPOINT_NAME = "_checkpoint.json"


def _path(user_dir: str | Path) -> Path:
    """Return the checkpoint file path of a user directory.

    Args:
        user_dir: Export directory of the user.

    Returns:
        Path of the checkpoint file.
    """
    return Path(user_dir) / CHECKPOINT_NAME


def load_checkpoint(user_dir: str | Path) -> dict:
    """Read the checkpoint data of a user from disk.

    Args:
        user_dir: Export directory of the user.

    Returns:
        Checkpoint dict with the written articles and the run timestamps.
    """
    p = _path(user_dir)
    if not p.exists():
        return {"written": {}, "last_run_at": None, "last_date": None}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"written": {}, "last_run_at": None, "last_date": None}
    data.setdefault("written", {})
    return data


def _entries(user_dir: str | Path, date: str) -> dict[str, str]:
    """Return the article records of a day with their processing status.

    Args:
        user_dir: Export directory of the user.
        date: Publication date as 'YYYY-MM-DD'.

    Returns:
        Dict mapping article id to analysis status ('GOLD' or 'L1_ONLY').
    """
    raw = load_checkpoint(user_dir).get("written", {}).get(date, {})
    if isinstance(raw, dict):
        return {str(k): str(v or "") for k, v in raw.items()}
    return {str(aid): "" for aid in (raw or [])}             # legacy list format


def written_ids(user_dir: str | Path, date: str) -> set[str]:
    """Return the article ids already recorded for a day.

    Args:
        user_dir: Export directory of the user.
        date: Publication date as 'YYYY-MM-DD'.

    Returns:
        Set of the article ids written.
    """
    return set(_entries(user_dir, date))


def filter_new(user_dir: str | Path, date: str, article_ids) -> list[str]:
    """Filter the article ids that were not yet exported on a day.

    Args:
        user_dir: Export directory of the user.
        date: Publication date as 'YYYY-MM-DD'.
        article_ids: Article ids to check.

    Returns:
        Deduplicated ids that are not in the checkpoint.
    """
    seen = written_ids(user_dir, date)
    out, dedup = [], set()
    for aid in article_ids:
        if aid not in seen and aid not in dedup:
            dedup.add(aid); out.append(aid)
    return out


def filter_upgraded(user_dir: str | Path, date: str, statuses: dict[str, str]) -> list[str]:
    """Filter the articles upgraded from L1_ONLY to GOLD.

    Args:
        user_dir: Export directory of the user.
        date: Publication date as 'YYYY-MM-DD'.
        statuses: Current status of the articles keyed by article id.

    Returns:
        Ids of the articles that just received Gold in-depth analysis.
    """
    prev = _entries(user_dir, date)
    return [aid for aid, st in statuses.items()
            if prev.get(aid) == "L1_ONLY" and st == "GOLD"]


def mark_written(user_dir: str | Path, date: str, article_ids, statuses=None) -> bool:
    """Record the exported articles in the checkpoint file.

    Args:
        user_dir: Export directory of the user.
        date: Publication date as 'YYYY-MM-DD'.
        article_ids: Ids of the articles written successfully.
        statuses: Optional status of each article keyed by article id.

    Returns:
        True if saved, False if the file is locked.
    """
    p = _path(user_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = load_checkpoint(user_dir)
    cur = _entries(user_dir, date)
    statuses = statuses or {}
    for aid in article_ids:
        cur[aid] = statuses.get(aid, cur.get(aid, ""))
    data["written"][date] = dict(sorted(cur.items()))
    data["last_run_at"] = now_vn_iso()
    data["last_date"] = date
    try:
        # safe_atomic_write uses a unique temp name (pid+uuid), so two parallel runs do not
        # overwrite each other as a fixed `_checkpoint.json.tmp` name would.
        # fallback_on_lock=False: a `_checkpoint_HHMMSS.json` snapshot is useless because nothing reads it.
        safe_atomic_write(p, json.dumps(data, ensure_ascii=False, indent=2),
                          fallback_on_lock=False, encoding="utf-8")
        return True
    except OSError as e:
        logger.warning("checkpoint bị khoá, bỏ qua ghi sổ (user={} date={}): {}", p.parent.name, date, e)
        return False
