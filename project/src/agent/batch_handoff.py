"""Unpack batch output files returned by agents into single records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def unpack_batch_output(batch_output: dict | list | str | Path) -> list[dict]:
    """Unpack a subagent batch output into single agent-output records.

    Supported formats:
    1. List of objects: [ {"article_id": "..."}, ... ]
    2. Dict with key 'outputs' or 'results': { "batch_id": "...", "outputs": [ ... ] }
    3. Single dict when the agent returns one article: { "article_id": "..." }

    Args:
        batch_output: Parsed output, or path to a JSON file that holds it.

    Returns:
        Records that carry an `article_id`; empty when the path does not exist or the format is unknown.
    """
    data: Any = batch_output
    if isinstance(data, (str, Path)):
        p = Path(data)
        if not p.exists():
            return []
        data = json.loads(p.read_text(encoding="utf-8"))

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict) and "article_id" in item]

    if isinstance(data, dict):
        if "outputs" in data and isinstance(data["outputs"], list):
            return [item for item in data["outputs"] if isinstance(item, dict) and "article_id" in item]
        if "results" in data and isinstance(data["results"], list):
            return [item for item in data["results"] if isinstance(item, dict) and "article_id" in item]
        if "article_id" in data:
            return [data]

    return []
