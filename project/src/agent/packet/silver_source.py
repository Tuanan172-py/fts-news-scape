"""Locate and read Silver-layer article bodies for the Article Lane."""
from __future__ import annotations

import json
from pathlib import Path

from src.core import paths

SILVER_ROOT = paths.silver_dir()


def silver_package_path(source_domain: str | None, published_at: str | None,
                         article_id: str) -> Path | None:
    """Find the Silver package of an article by the store layout.

    The Silver layout is `<data_root>/silver/<domain>/<yyyymmdd>/<hash>.json`. The date
    is the package build date, not the publication date, so the exact date is tried
    first and the other dates of the same domain are scanned on a miss.

    Args:
        source_domain: Source domain, for example `vneconomy.vn`.
        published_at: Publication timestamp, for example `2026-10-05T...`.
        article_id: Article identity hash (`url_title_hash`).

    Returns:
        Package path when the file exists, None when inputs are missing or no file is found.
    """
    try:
        if not source_domain or not article_id:
            return None
        day = (published_at or "")[:10].replace("-", "")
        if len(day) == 8 and day.isdigit():
            candidate = SILVER_ROOT / source_domain / day / f"{article_id}.json"
            if candidate.is_file():
                return candidate
        matches = sorted((SILVER_ROOT / source_domain).glob(f"*/{article_id}.json"))
        return matches[-1] if matches else None
    except (TypeError, ValueError, OSError):
        return None


def read_silver_text(source_domain: str | None, published_at: str | None,
                      article_id: str) -> str:
    """Read the `cleaned_text` field of a Silver package.

    Args:
        source_domain: Source domain.
        published_at: Publication timestamp.
        article_id: Article identity hash.

    Returns:
        Full article body, or an empty string when no readable Silver package exists.
    """
    path = silver_package_path(source_domain, published_at, article_id)
    if path is None:
        return ""
    try:
        return (json.loads(path.read_text(encoding="utf-8")) or {}).get("cleaned_text") or ""
    except (OSError, ValueError):
        return ""
