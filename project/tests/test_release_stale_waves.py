"""Tests for release_stale_waves maintenance script."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.maintenance.release_stale_waves import release_stale_waves
from src.ops.config import resolve_paths
from src.ops.store import OpsStore, now_vn, iso


@pytest.fixture
def ops_store(tmp_path, monkeypatch):
    """Set up an isolated OpsStore in a temporary directory."""
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(tmp_path / "data"))
    paths = resolve_paths()
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.log_dir.mkdir(parents=True, exist_ok=True)
    store = OpsStore(paths.ops_db, log_dir=paths.log_dir)
    return store


def test_release_stale_waves_clears_failed_and_parked_including_historical_prefixes(ops_store):
    """Verify that FAILED and PARKED waves (including W1023 historical prefixes) are released."""
    now = iso(now_vn())

    # Create stale waves with historical prefix W1023 and regular waves
    ops_store.upsert_wave(
        wave_id="W10231200_01",
        trigger="manual",
        status="FAILED",
        reason="Simulated network failure",
        n_articles=2,
        opened_at=now,
    )
    ops_store.record_wave_articles("W10231200_01", ["art_01", "art_02"])

    ops_store.upsert_wave(
        wave_id="W_PARKED_01",
        trigger="manual",
        status="PARKED",
        reason="Simulated breaker park",
        n_articles=1,
        opened_at=now,
    )
    ops_store.record_wave_articles("W_PARKED_01", ["art_03"])

    # Before release, articles must be reserved
    assert ops_store.reserved_article_ids() == {"art_01", "art_02", "art_03"}

    # Execute release
    cancelled = release_stale_waves()
    assert cancelled == 2

    # After release, queue must be unblocked
    assert ops_store.reserved_article_ids() == set()


def test_release_stale_waves_no_candidates(ops_store):
    """Verify return code when no stale waves exist."""
    cancelled = release_stale_waves()
    assert cancelled == 0
    assert ops_store.reserved_article_ids() == set()


def test_release_stale_waves_include_active(ops_store):
    """Verify that include_active=True releases non-terminal waves as well."""
    now = iso(now_vn())

    ops_store.upsert_wave(
        wave_id="W_STUCK_ACTIVE",
        trigger="manual",
        status="PREPARED",
        n_articles=1,
        opened_at=now,
    )
    ops_store.record_wave_articles("W_STUCK_ACTIVE", ["art_active"])

    # Default release does not touch active waves
    assert release_stale_waves(include_active=False) == 0
    assert ops_store.reserved_article_ids() == {"art_active"}

    # With include_active=True, stuck active waves are cancelled
    assert release_stale_waves(include_active=True) == 1
    assert ops_store.reserved_article_ids() == set()
