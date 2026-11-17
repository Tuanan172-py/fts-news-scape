"""Adversarial concurrency test suite for hardened SQLite WAL checkpointing."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from project.scripts.maintenance.audit_m4_m5_integrity import (
    REQUIRED_V2_LEAN_FIELDS,
    audit_and_truncate_wal,
    run_full_audit,
)


@pytest.fixture
def isolated_wal_db(tmp_path: Path) -> Path:
    """Create an isolated SQLite database initialized in WAL mode."""
    db_file = tmp_path / "test_concurrency.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO records (value) VALUES ('initial_seed')")
    conn.commit()
    conn.close()
    return db_file


def test_wal_checkpoint_under_concurrent_writer_lock(isolated_wal_db: Path) -> None:
    """Verify wal_checkpoint waits for an active writer transaction to clear."""
    db_path = str(isolated_wal_db)

    def writer_worker() -> None:
        conn = sqlite3.connect(db_path, timeout=10.0)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE records SET value = 'locked_write' WHERE id = 1")
        time.sleep(3.0)
        conn.commit()
        conn.close()

    writer_thread = threading.Thread(target=writer_worker)
    writer_thread.start()
    time.sleep(0.5)

    start_time = time.time()
    result = audit_and_truncate_wal(isolated_wal_db)
    elapsed = time.time() - start_time

    writer_thread.join()

    assert elapsed >= 2.0
    assert result["integrity_check"] == "ok"
    assert result["checkpoint"]["busy"] == 0
    assert result["clean_wal_truncated"] is True
    assert result["wal_size_bytes"] == 0


def test_wal_checkpoint_under_concurrent_reader_lock_active_wal(isolated_wal_db: Path) -> None:
    """Verify wal_checkpoint waits for reader holding active uncheckpointed WAL frames."""
    db_path = str(isolated_wal_db)

    conn_seed = sqlite3.connect(db_path)
    conn_seed.execute("INSERT INTO records (value) VALUES ('wal_frame_1')")
    conn_seed.commit()

    def reader_worker() -> None:
        conn = sqlite3.connect(db_path, timeout=10.0)
        conn.execute("BEGIN")
        conn.execute("SELECT * FROM records").fetchall()
        time.sleep(3.5)
        conn.commit()
        conn.close()

    reader_thread = threading.Thread(target=reader_worker)
    reader_thread.start()
    time.sleep(0.5)

    conn_seed.execute("INSERT INTO records (value) VALUES ('wal_frame_2')")
    conn_seed.commit()

    start_time = time.time()
    result = audit_and_truncate_wal(isolated_wal_db)
    elapsed = time.time() - start_time

    reader_thread.join()
    conn_seed.close()

    assert elapsed >= 2.5
    assert result["integrity_check"] == "ok"
    assert result["checkpoint"]["busy"] == 0
    assert result["clean_wal_truncated"] is True
    assert result["wal_size_bytes"] == 0


def test_wal_checkpoint_under_rapid_concurrent_burst(isolated_wal_db: Path) -> None:
    """Verify wal_checkpoint succeeds under concurrent read and write bursts."""
    db_path = str(isolated_wal_db)
    stop_event = threading.Event()

    def reader_burst() -> None:
        while not stop_event.is_set():
            try:
                conn = sqlite3.connect(db_path, timeout=2.0)
                conn.execute("BEGIN")
                conn.execute("SELECT COUNT(*) FROM records").fetchone()
                time.sleep(0.05)
                conn.commit()
                conn.close()
            except sqlite3.OperationalError:
                pass

    def writer_burst() -> None:
        while not stop_event.is_set():
            try:
                conn = sqlite3.connect(db_path, timeout=2.0)
                conn.execute("INSERT INTO records (value) VALUES ('burst_payload')")
                conn.commit()
                conn.close()
                time.sleep(0.1)
            except sqlite3.OperationalError:
                pass

    threads = [
        threading.Thread(target=reader_burst),
        threading.Thread(target=reader_burst),
        threading.Thread(target=writer_burst),
    ]

    for t in threads:
        t.start()

    time.sleep(0.5)
    result = audit_and_truncate_wal(isolated_wal_db)

    stop_event.set()
    for t in threads:
        t.join()

    assert result["integrity_check"] == "ok"
    assert result["checkpoint"]["busy"] == 0
    assert result["clean_wal_truncated"] is True
    assert result["wal_size_bytes"] == 0


def test_wal_checkpoint_persistent_contention_graceful_rejection(isolated_wal_db: Path, monkeypatch) -> None:
    """Verify wal_checkpoint returns structured rejection when lock contention persists."""
    db_path = str(isolated_wal_db)

    # Seed WAL frames
    conn_seed = sqlite3.connect(db_path)
    conn_seed.execute("INSERT INTO records (value) VALUES ('seed_dirty_wal')")
    conn_seed.commit()

    # Reader connection holds uncommitted transaction on WAL frames
    conn_lock = sqlite3.connect(db_path, timeout=10.0)
    conn_lock.execute("BEGIN")
    conn_lock.execute("SELECT * FROM records").fetchall()

    # Monkeypatch time.sleep to avoid waiting real seconds in retry loop
    monkeypatch.setattr(time, "sleep", lambda s: None)

    # Force busy_timeout to 50ms so checkpoint immediately encounters busy=1 on each retry
    def fast_audit(path: Path) -> dict:
        conn = sqlite3.connect(str(path), timeout=0.1)
        try:
            c = conn.cursor()
            c.execute("PRAGMA busy_timeout = 50")
            integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
            c.execute("PRAGMA wal_checkpoint(RESTART)")
            busy = 1
            log_pages = checkpointed_pages = -1
            for _ in range(10):
                res = c.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                busy, log_pages, checkpointed_pages = res
                if busy == 0:
                    break
                time.sleep(0.01)
        finally:
            conn.close()

        wal_file = path.parent / f"{path.name}-wal"
        shm_file = path.parent / f"{path.name}-shm"
        wal_size = wal_file.stat().st_size if wal_file.exists() else 0
        shm_size = shm_file.stat().st_size if shm_file.exists() else 0

        return {
            "integrity_check": integrity,
            "checkpoint": {
                "busy": busy,
                "log_pages": log_pages,
                "checkpointed_pages": checkpointed_pages,
            },
            "wal_size_bytes": wal_size,
            "clean_wal_truncated": wal_size == 0 and busy == 0,
        }

    res = fast_audit(isolated_wal_db)
    conn_lock.rollback()
    conn_lock.close()
    conn_seed.close()

    assert res["checkpoint"]["busy"] == 1
    assert res["clean_wal_truncated"] is False


def test_full_audit_lifecycle_under_isolated_concurrency(tmp_path: Path, monkeypatch) -> None:
    """Verify run_full_audit completes end-to-end under concurrent lock contention."""
    db_file = tmp_path / "monocle.db"
    monkeypatch.setenv("MONOCLE_DB_PATH", str(db_file))

    conn = sqlite3.connect(str(db_file))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(
        "CREATE TABLE agent_outputs (article_id TEXT PRIMARY KEY, dod_pass INTEGER, payload TEXT)"
    )
    conn.execute("INSERT INTO agent_outputs VALUES ('art_001', 1, '{}')")
    conn.commit()
    conn.close()

    # Create mock output dir and file
    out_dir = tmp_path / "agent_outputs" / "_article"
    out_dir.mkdir(parents=True, exist_ok=True)
    mock_wave = "W_TEST_99"
    out_file = out_dir / f"article_{mock_wave}_01.output.json"
    dummy_record = {k: "val" if k != "c" else [0] for k in REQUIRED_V2_LEAN_FIELDS}
    out_file.write_text(json.dumps([dummy_record]), encoding="utf-8")

    from src.core import paths
    monkeypatch.setattr(paths, "agent_outputs_dir", lambda lane: out_dir)

    # Spawn locker holding write lock for 2 seconds
    def temporary_locker() -> None:
        c = sqlite3.connect(str(db_file), timeout=10.0)
        c.execute("BEGIN IMMEDIATE")
        time.sleep(2.0)
        c.rollback()
        c.close()

    lock_thread = threading.Thread(target=temporary_locker)
    lock_thread.start()
    time.sleep(0.5)

    start_time = time.time()
    success, report = run_full_audit(mock_wave, as_json=True)
    elapsed = time.time() - start_time

    lock_thread.join()

    assert elapsed >= 1.5
    assert success is True
    assert report["verdict"] == "APPROVE"
    assert report["database_integrity_and_wal"]["checkpoint"]["busy"] == 0
    assert report["database_integrity_and_wal"]["clean_wal_truncated"] is True
