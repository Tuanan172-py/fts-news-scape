"""Empirical challenger verification harness for Milestone 2 ops queue and rolling wave packaging.

Instance: challenger_m2_2
Verifies:
1. Ops queue state: verify_ops_queue.py reports 0 unreleased reserved articles.
2. Wave state: wave W_BKL_01_10301528 is confirmed marked DONE in production ops.db.
3. Wave packaging: next wave packs cleanly with Tier 1 priority ordering.
4. Lifecycle cleanup: release_stale_waves unblocks parked waves to leave 0 reserved articles.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.maintenance.release_stale_waves import release_stale_waves
from src.ops.config import resolve_paths
from src.ops.store import OpsStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WAVE_DONE_ID = "W_BKL_01_10301528"


def clean_ops_env() -> dict[str, str]:
    """Build environment for subprocesses pointing to operational data root.

    Strips pytest-induced MONOCLE_* environment overrides so child scripts
    reach the actual operational data in C:\\data\\news-scape.

    Returns:
        Environment dictionary with operational defaults.
    """
    env = dict(os.environ)
    env.pop("MONOCLE_DATA_DIR", None)
    env.pop("MONOCLE_DB_PATH", None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


@pytest.mark.production_host
def test_verify_ops_queue_cli_unblocked():
    """Verify that verify_ops_queue.py confirms the queue is unblocked with 0 reserved articles."""
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "maintenance" / "verify_ops_queue.py"),
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=clean_ops_env(),
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"verify_ops_queue.py failed with code {proc.returncode}:\n{proc.stderr}"
    assert "Unreleased reserved articles (SQL): 0" in proc.stdout
    assert "Reserved article ids (read-only)   : 0" in proc.stdout
    assert "QUEUE UNBLOCKED (0 reserved articles). READY FOR PROCESSING." in proc.stdout


@pytest.mark.production_host
def test_wave_w_bkl_01_is_marked_done_in_ops_db():
    """Verify via subprocess query that wave W_BKL_01_10301528 is marked DONE in production ops.db."""
    code = (
        "from src.core.stdio import force_utf8_stdio; force_utf8_stdio(); "
        "import sqlite3; from src.ops.config import resolve_paths; "
        "conn = sqlite3.connect(f'file:{resolve_paths().ops_db}?mode=ro', uri=True); "
        f"r = conn.execute('SELECT wave_id, status FROM ops_waves WHERE wave_id=\"{WAVE_DONE_ID}\"').fetchone(); "
        "assert r is not None, 'Wave not found'; "
        "assert r[1] == 'DONE', f'Expected status DONE, got {r[1]}'; "
        "print('STATUS_OK', r[0], r[1])"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(PROJECT_ROOT),
        env=clean_ops_env(),
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"Query failed with code {proc.returncode}:\n{proc.stderr}"
    assert f"STATUS_OK {WAVE_DONE_ID} DONE" in proc.stdout


@pytest.mark.production_host
def test_manifest_priority_queue_ordering():
    """Verify that packed wave manifest maintains Tier 1 priority over Tier 2/3."""
    manifest_path = Path(r"C:\data\news-scape\agent_tasks\article\wave_W_BKL_01_10301528.json")
    if not manifest_path.exists():
        pytest.skip(f"Manifest not found: {manifest_path}")

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data.get("articles", 0) == 498
    assert data.get("tier1", 0) == 290

    batches = data.get("batches", [])
    assert len(batches) == 10

    # Batches 0-4 are 100% Tier 1 (50/50)
    for b in batches[:5]:
        assert b.get("n") == 50
        assert b.get("tier1") == 50, f"Expected 50 tier1 items, got {b.get('tier1')}"

    # Batch 5 has the remaining 40 Tier 1 items
    assert batches[5].get("n") == 50
    assert batches[5].get("tier1") == 40

    # Batches 6-9 are strictly Tier 2/3 (0 tier1)
    for b in batches[6:]:
        assert b.get("tier1") == 0

    # Confirm monotonic non-increasing tier1 proportion (priority queue invariant)
    tier1_ratios = [b.get("tier1", 0) / b.get("n", 1) for b in batches]
    for i in range(len(tier1_ratios) - 1):
        assert tier1_ratios[i] >= tier1_ratios[i + 1], "Tier 1 ratio must be monotonically non-increasing"


def test_isolated_parked_wave_release_lifecycle(tmp_path, monkeypatch):
    """Stress test: verify parked wave creation and release_stale_waves unblocking."""
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(tmp_path / "test_data"))
    paths = resolve_paths()
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.log_dir.mkdir(parents=True, exist_ok=True)
    store = OpsStore(paths.ops_db, log_dir=paths.log_dir)

    wid = "W_TEST_DRYRUN_M2_2"
    store.upsert_wave(wid, trigger="manual", status="PARKED", n_articles=50, opened_at="2026-10-30T10:00:00Z")
    store.record_wave_articles(wid, [f"art_test_{i:03d}" for i in range(50)])

    assert len(store.reserved_article_ids()) == 50

    cancelled = release_stale_waves(include_active=False)
    assert cancelled == 1
    assert len(store.reserved_article_ids()) == 0
    assert store.wave(wid)["status"] == "CANCELLED"
