"""Adapt L1 entity classification for the conformance test suite."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.l1_classifier import classify_title            # noqa: E402
from src.agent.l1_router import build_code_first_output       # noqa: E402
from src.agent.l1_router import check_l1_dod                  # noqa: E402,F401  (re-export)

__all__ = ["build_l1_output", "check_l1_dod"]


def build_l1_output(task: dict) -> dict:
    """Build a standard L1 classification result from the article title in a work package.

    Args:
        task: L1 work package dict containing `article_id` and `title`.

    Returns:
        Entity result dict conforming to the l1-entity-output-v1 schema.
    """
    rec = classify_title(task["title"])
    return build_code_first_output(rec, task["article_id"])
