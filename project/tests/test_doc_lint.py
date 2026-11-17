"""Deprecated test file migrated to tests/test_knowledge.py under Milestone M2 (Wave W-B)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "project/scripts"))

import doc_lint as dl  # noqa: E402


def test_doc_lint_decommissioned_stub():
    """Verify legacy doc_lint stub exports remain accessible."""
    assert hasattr(dl, "lint_python")
    assert hasattr(dl, "lint_html")
    assert hasattr(dl, "lint_markdown")
    assert hasattr(dl, "lint_repo")
    assert hasattr(dl, "Finding")
