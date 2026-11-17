"""Empirical challenger verification harness for Milestone 1 queue unblocking.

Verifies:
1. Isolated OpsStore queue state and direct SQL invariants for reserved articles.
2. Idempotency stress test: rapid successive calls to release_stale_waves() under normal and --all flags.
3. Complex synthetic stress test: diverse wave lifecycles, ensuring non-terminal waves are cleanly cancelled.
4. CLI subprocess execution of verify_ops_queue.py and release_stale_waves.py through piped stdout.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.maintenance.release_stale_waves import release_stale_waves
from src.ops.config import resolve_paths
from src.ops.store import OpsStore, now_vn, iso, RELEASED_WAVE_STATUSES

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def isolated_ops(tmp_path, monkeypatch):
    """Isolated OpsStore for synthetic stress testing."""
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(tmp_path / "stress_data"))
    paths = resolve_paths()
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.log_dir.mkdir(parents=True, exist_ok=True)
    return OpsStore(paths.ops_db, log_dir=paths.log_dir)


def test_isolated_zero_reserved_articles_direct_sql(isolated_ops):
    """Verify that an empty OpsStore reports exactly 0 reserved articles via direct SQL."""
    with isolated_ops.conn() as c:
        marks = ",".join("?" * len(RELEASED_WAVE_STATUSES))
        query = (
            "SELECT COUNT(DISTINCT a.article_id) "
            "FROM ops_wave_articles a "
            "JOIN ops_waves w ON w.wave_id = a.wave_id "
            f"WHERE w.status NOT IN ({marks})"
        )
        count = c.execute(query, RELEASED_WAVE_STATUSES).fetchone()[0]
        assert count == 0
    assert isolated_ops.reserved_article_ids() == set()


def test_synthetic_stress_lifecycle_idempotency(isolated_ops):
    """Synthetic stress test: multiple waves in varying states, repeated release cycles."""
    now = iso(now_vn())

    # Create a batch of waves: 10 FAILED, 10 PARKED, 10 DONE, 5 CANCELLED, 5 ANALYZING
    for i in range(10):
        wid = f"W_FAIL_{i:02d}"
        isolated_ops.upsert_wave(wid, trigger="manual", status="FAILED", n_articles=5, opened_at=now)
        isolated_ops.record_wave_articles(wid, [f"art_fail_{i}_{j}" for j in range(5)])

    for i in range(10):
        wid = f"W_PARK_{i:02d}"
        isolated_ops.upsert_wave(wid, trigger="manual", status="PARKED", n_articles=5, opened_at=now)
        isolated_ops.record_wave_articles(wid, [f"art_park_{i}_{j}" for j in range(5)])

    for i in range(10):
        wid = f"W_DONE_{i:02d}"
        isolated_ops.upsert_wave(wid, trigger="manual", status="DONE", n_articles=5, opened_at=now)
        isolated_ops.record_wave_articles(wid, [f"art_done_{i}_{j}" for j in range(5)])

    for i in range(5):
        wid = f"W_CANC_{i:02d}"
        isolated_ops.upsert_wave(wid, trigger="manual", status="CANCELLED", n_articles=5, opened_at=now)
        isolated_ops.record_wave_articles(wid, [f"art_canc_{i}_{j}" for j in range(5)])

    for i in range(5):
        wid = f"W_ACT_{i:02d}"
        isolated_ops.upsert_wave(wid, trigger="manual", status="ANALYZING", n_articles=5, opened_at=now)
        isolated_ops.record_wave_articles(wid, [f"art_act_{i}_{j}" for j in range(5)])

    # Initial check: 10*5 + 10*5 + 5*5 = 125 reserved articles
    reserved_initial = isolated_ops.reserved_article_ids()
    assert len(reserved_initial) == 125

    # First release pass: releases 10 FAILED + 10 PARKED = 20 waves
    cancelled = release_stale_waves(include_active=False)
    assert cancelled == 20

    # Remaining reserved should be only the 5 ANALYZING waves (25 articles)
    assert len(isolated_ops.reserved_article_ids()) == 25

    # Repeated releases without include_active must be strictly idempotent (0 cancelled)
    for _ in range(15):
        assert release_stale_waves(include_active=False) == 0
        assert len(isolated_ops.reserved_article_ids()) == 25

    # Now release with include_active=True: releases the 5 ANALYZING waves
    cancelled_all = release_stale_waves(include_active=True)
    assert cancelled_all == 5
    assert len(isolated_ops.reserved_article_ids()) == 0

    # Repeated releases with include_active must be strictly idempotent (0 cancelled)
    for _ in range(15):
        assert release_stale_waves(include_active=True) == 0
        assert len(isolated_ops.reserved_article_ids()) == 0


def test_verify_ops_queue_cli_runs_clean():
    """Verify that verify_ops_queue.py executes cleanly through subprocess pipe."""
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "maintenance" / "verify_ops_queue.py")],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"Script failed with code {proc.returncode}:\n{proc.stderr}"
    assert "QUEUE UNBLOCKED (0 reserved articles)" in proc.stdout
