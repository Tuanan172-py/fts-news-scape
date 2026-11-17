"""Extreme adversarial stress-test of database concurrency, lock contention, and WAL truncation."""
from __future__ import annotations

import concurrent.futures
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.stdio import force_utf8_stdio
from src.ops.config import resolve_paths
from src.db.preflight import resolve_db_path

force_utf8_stdio()


def stress_worker_monocle(db_path: Path, worker_id: int, iterations: int = 5) -> dict[str, Any]:
    """Execute repetitive read queries under high concurrency on monocle.db.

    Args:
        db_path: Path to monocle.db SQLite file.
        worker_id: Numerical ID of worker thread.
        iterations: Number of query iterations to run.

    Returns:
        Dictionary summarizing execution status and elapsed time.
    """
    t0 = time.perf_counter()
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA busy_timeout = 30000")
        total_rows = 0
        for _ in range(iterations):
            # Aggregation query
            agg = cur.execute(
                "SELECT count(*), count(distinct article_id), sum(dod_pass) FROM agent_outputs"
            ).fetchone()
            # Random slice read
            slice_rows = cur.execute(
                "SELECT article_id, dod_pass FROM agent_outputs ORDER BY rowid DESC LIMIT 25"
            ).fetchall()
            total_rows += len(slice_rows) + (agg[0] if agg else 0)

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {"worker_id": worker_id, "status": "ok", "total_rows": total_rows, "elapsed_ms": elapsed_ms}
    except Exception as exc:
        return {"worker_id": worker_id, "status": "error", "error": str(exc), "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2)}
    finally:
        conn.close()


def stress_worker_ops(db_path: Path, worker_id: int, iterations: int = 5) -> dict[str, Any]:
    """Execute repetitive read queries under high concurrency on ops.db.

    Args:
        db_path: Path to ops.db SQLite file.
        worker_id: Numerical ID of worker thread.
        iterations: Number of query iterations to run.

    Returns:
        Dictionary summarizing execution status and elapsed time.
    """
    t0 = time.perf_counter()
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA busy_timeout = 30000")
        total_rows = 0
        for _ in range(iterations):
            w = cur.execute("SELECT status, count(*) FROM ops_waves GROUP BY status").fetchall()
            a = cur.execute("SELECT count(*) FROM ops_wave_articles").fetchone()[0]
            total_rows += len(w) + a

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {"worker_id": worker_id, "status": "ok", "total_rows": total_rows, "elapsed_ms": elapsed_ms}
    except Exception as exc:
        return {"worker_id": worker_id, "status": "error", "error": str(exc), "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2)}
    finally:
        conn.close()


def run_extreme_stress_test(num_monocle_threads: int = 24, num_ops_threads: int = 8) -> bool:
    """Run concurrent load test with simultaneous reader threads and check wal_checkpoint.

    Args:
        num_monocle_threads: Number of simultaneous reader threads for monocle.db.
        num_ops_threads: Number of simultaneous reader threads for ops.db.

    Returns:
        True if all threads completed with 0 errors and WAL truncated cleanly; False otherwise.
    """
    monocle_db = resolve_db_path()
    paths = resolve_paths()
    ops_db = paths.ops_db

    print("=" * 80)
    print(f" 🔥 EXTREME CONCURRENCY STRESS TEST: {num_monocle_threads} MONOCLE READERS + {num_ops_threads} OPS READERS")
    print("=" * 80)

    total_threads = num_monocle_threads + num_ops_threads
    t0 = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=total_threads) as executor:
        futures = []
        for i in range(num_monocle_threads):
            futures.append(executor.submit(stress_worker_monocle, monocle_db, i, 10))
        for j in range(num_ops_threads):
            futures.append(executor.submit(stress_worker_ops, ops_db, 100 + j, 10))

        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    total_time_ms = round((time.perf_counter() - t0) * 1000, 2)
    errors = [r for r in results if r["status"] != "ok"]

    print(f"Total concurrent tasks completed: {len(results)}")
    print(f"Total errors encountered: {len(errors)}")
    print(f"Execution time: {total_time_ms:.2f} ms")

    if errors:
        for err in errors[:5]:
            print(f"  Error: {err}")
        return False

    # Checkpoint and verify WAL truncation
    print("\nExecuting PRAGMA wal_checkpoint(TRUNCATE) following concurrent read saturation...")
    conn = sqlite3.connect(str(monocle_db), timeout=60.0)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA busy_timeout = 60000")
        cp = cur.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        busy, log_pages, checkpointed = cp
        print(f"  wal_checkpoint(TRUNCATE): busy={busy}, log_pages={log_pages}, checkpointed={checkpointed}")
        integrity = cur.execute("PRAGMA integrity_check").fetchone()[0]
        print(f"  PRAGMA integrity_check: {integrity}")
    finally:
        conn.close()

    wal_file = monocle_db.parent / f"{monocle_db.name}-wal"
    wal_size = wal_file.stat().st_size if wal_file.exists() else 0
    print(f"  Final WAL file size: {wal_size:,} bytes")

    success = (len(errors) == 0 and busy == 0 and wal_size == 0 and integrity == "ok")
    if success:
        print("\n🏆 ADVERSARIAL STRESS TEST VERDICT: APPROVE (Zero contention under saturation)")
    else:
        print("\n❌ ADVERSARIAL STRESS TEST VERDICT: REQUEST_CHANGES (Contention or truncation failure)")

    return success


if __name__ == "__main__":
    passed = run_extreme_stress_test()
    sys.exit(0 if passed else 1)
