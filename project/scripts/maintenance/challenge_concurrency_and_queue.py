"""Adversarial stress-testing of database integrity, reservation queue, and concurrency."""
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
from src.ops.store import RELEASED_WAVE_STATUSES

force_utf8_stdio()


def check_ops_db(ops_db_path: Path) -> dict[str, Any]:
    """Audit ops.db for integrity, orphan waves, unreleased reservations, and file lock state."""
    results: dict[str, Any] = {}

    conn = sqlite3.connect(f"file:{ops_db_path}?mode=ro", uri=True, timeout=30.0)
    try:
        cur = conn.cursor()

        # 1. Integrity check
        t0 = time.perf_counter()
        integrity = cur.execute("PRAGMA integrity_check").fetchone()[0]
        results["integrity_check"] = integrity
        results["integrity_check_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        # 2. Wave distribution
        waves = cur.execute("SELECT status, count(*) FROM ops_waves GROUP BY status").fetchall()
        results["wave_distribution"] = dict(waves)

        # 3. Active / Non-terminal waves
        marks = ",".join("?" * len(RELEASED_WAVE_STATUSES))
        active_waves = cur.execute(
            f"SELECT wave_id, status, opened_at, updated_at FROM ops_waves WHERE status NOT IN ({marks})",
            RELEASED_WAVE_STATUSES,
        ).fetchall()
        results["active_non_terminal_waves"] = active_waves

        # 4. Unreleased articles in ops_wave_articles
        unreleased = cur.execute(
            f"SELECT count(DISTINCT a.article_id) FROM ops_wave_articles a "
            f"JOIN ops_waves w ON w.wave_id = a.wave_id WHERE w.status NOT IN ({marks})",
            RELEASED_WAVE_STATUSES,
        ).fetchone()[0]
        results["unreleased_reserved_articles"] = unreleased

        # 5. Check wave W_BKL_01_11021334 specifically
        wave_specific = cur.execute(
            "SELECT wave_id, status, opened_at, updated_at FROM ops_waves WHERE wave_id = 'W_BKL_01_11021334'"
        ).fetchone()
        results["target_wave"] = wave_specific

        w_articles_count = cur.execute(
            "SELECT count(*) FROM ops_wave_articles WHERE wave_id = 'W_BKL_01_11021334'"
        ).fetchone()[0]
        results["target_wave_articles_assigned"] = w_articles_count

    finally:
        conn.close()

    # Physical files
    wal_file = ops_db_path.parent / f"{ops_db_path.name}-wal"
    shm_file = ops_db_path.parent / f"{ops_db_path.name}-shm"
    results["db_size_bytes"] = ops_db_path.stat().st_size
    results["wal_size_bytes"] = wal_file.stat().st_size if wal_file.exists() else 0
    results["shm_size_bytes"] = shm_file.stat().st_size if shm_file.exists() else 0

    return results


def concurrent_reader_worker(db_path: Path, worker_id: int) -> dict[str, Any]:
    """Perform reads on monocle.db in read-only mode to stress concurrent read throughput."""
    t0 = time.perf_counter()
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA busy_timeout = 30000")
        total_articles = cur.execute("SELECT count(*) FROM articles").fetchone()[0]
        recent_outputs = cur.execute(
            "SELECT article_id, dod_pass, length(output_json) "
            "FROM agent_outputs ORDER BY rowid DESC LIMIT 50"
        ).fetchall()
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "worker_id": worker_id,
            "status": "ok",
            "articles_count": total_articles,
            "rows_read": len(recent_outputs),
            "elapsed_ms": elapsed_ms,
        }
    except Exception as exc:
        return {
            "worker_id": worker_id,
            "status": "error",
            "error": str(exc),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
    finally:
        conn.close()


def test_monocle_concurrency(db_path: Path, num_threads: int = 10) -> dict[str, Any]:
    """Stress-test concurrent read throughput across multiple threads."""
    t0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(concurrent_reader_worker, db_path, i) for i in range(num_threads)]
        worker_results = [f.result() for f in concurrent.futures.as_completed(futures)]

    total_time_ms = round((time.perf_counter() - t0) * 1000, 2)
    errors = [r for r in worker_results if r["status"] != "ok"]

    return {
        "threads_launched": num_threads,
        "errors_count": len(errors),
        "errors": errors,
        "total_time_ms": total_time_ms,
        "worker_results": worker_results,
    }


def check_harness_db(harness_db_path: Path) -> dict[str, Any]:
    """Audit harness.db for integrity and trace continuity."""
    results: dict[str, Any] = {}
    if not harness_db_path.exists():
        results["exists"] = False
        return results

    uri = f"file:{harness_db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    try:
        cur = conn.cursor()
        integrity = cur.execute("PRAGMA quick_check").fetchone()[0]
        results["integrity"] = integrity

        ledger_entry = cur.execute(
            "SELECT wave, ts, n_items, billed_usd FROM token_ledger WHERE wave = 'W_BKL_01_11021334'"
        ).fetchone()
        results["target_wave_ledger"] = ledger_entry
    finally:
        conn.close()

    return results


def main() -> None:
    """Run all adversarial checks and output forensic diagnostics."""
    paths = resolve_paths()
    from src.db.preflight import resolve_db_path

    monocle_db = resolve_db_path()
    ops_db = paths.ops_db
    harness_db = PROJECT_ROOT.parent / "harness.db"

    print("=" * 80)
    print(" ⚔️ ADVERSARIAL CHALLENGER: CONCURRENCY & OPS QUEUE STRESS HARNESS")
    print("=" * 80)

    # 1. Ops.db check
    print("\n[CHALLENGE 1] OPS.DB QUEUE & INTEGRITY STRESS-TEST")
    ops_res = check_ops_db(ops_db)
    print(f"  ops.db path: {ops_db}")
    print(f"  PRAGMA integrity_check: {ops_res['integrity_check']} ({ops_res['integrity_check_ms']} ms)")
    print(f"  Wave distribution: {ops_res['wave_distribution']}")
    print(f"  Active non-terminal waves: {len(ops_res['active_non_terminal_waves'])}")
    print(f"  Unreleased reserved articles: {ops_res['unreleased_reserved_articles']}")
    print(f"  Target wave (W_BKL_01_11021334): {ops_res['target_wave']}")
    print(f"  Target wave assigned articles: {ops_res['target_wave_articles_assigned']}")
    print(f"  Physical DB size: {ops_res['db_size_bytes']:,} bytes | WAL: {ops_res['wal_size_bytes']:,} bytes | SHM: {ops_res['shm_size_bytes']:,} bytes")

    # 2. Monocle.db concurrent read stress test
    print("\n[CHALLENGE 2] MONOCLE.DB CONCURRENCY STRESS-TEST (10 THREADS SIMULTANEOUS READS)")
    concurrency_res = test_monocle_concurrency(monocle_db, num_threads=10)
    print(f"  Concurrent threads: {concurrency_res['threads_launched']}")
    print(f"  Errors encountered: {concurrency_res['errors_count']}")
    if concurrency_res['errors_count'] > 0:
        print(f"  First error: {concurrency_res['errors'][0]}")
    print(f"  Total concurrency execution time: {concurrency_res['total_time_ms']} ms")
    latencies = [r["elapsed_ms"] for r in concurrency_res["worker_results"] if r["status"] == "ok"]
    if latencies:
        print(f"  Read Latency (ms): min={min(latencies)}, avg={sum(latencies)/len(latencies):.2f}, max={max(latencies)}")

    # 3. Harness.db check
    print("\n[CHALLENGE 3] HARNESS.DB INTEGRITY & TOKEN LEDGER")
    harness_res = check_harness_db(harness_db)
    print(f"  PRAGMA quick_check: {harness_res.get('integrity')}")
    print(f"  Target wave ledger entry: {harness_res.get('target_wave_ledger')}")

    # Physical checks & WAL Checkpoint on monocle.db
    print("\n[CHALLENGE 4] MONOCLE.DB WAL CHECKPOINT & LOCK CONTENTION TEST")
    conn_wal = sqlite3.connect(str(monocle_db), timeout=60.0)
    try:
        cur_wal = conn_wal.cursor()
        cur_wal.execute("PRAGMA busy_timeout = 60000")
        pre_wal_file = monocle_db.parent / f"{monocle_db.name}-wal"
        pre_wal_size = pre_wal_file.stat().st_size if pre_wal_file.exists() else 0
        print(f"  Pre-checkpoint WAL size: {pre_wal_size:,} bytes")

        # Run checkpoint TRUNCATE
        cp_res = cur_wal.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        busy, log_pages, checkpointed = cp_res
        print(f"  PRAGMA wal_checkpoint(TRUNCATE): busy={busy}, log_pages={log_pages}, checkpointed={checkpointed}")

        integrity = cur_wal.execute("PRAGMA integrity_check").fetchone()[0]
        print(f"  PRAGMA integrity_check: {integrity}")
    finally:
        conn_wal.close()

    wal_file = monocle_db.parent / f"{monocle_db.name}-wal"
    shm_file = monocle_db.parent / f"{monocle_db.name}-shm"
    post_wal_size = wal_file.stat().st_size if wal_file.exists() else 0
    shm_size = shm_file.stat().st_size if shm_file.exists() else 0

    print(f"  Post-checkpoint WAL size: {post_wal_size:,} bytes")
    print(f"  SHM size: {shm_size:,} bytes")

    # Final verdict
    ops_ok = (
        ops_res["integrity_check"] == "ok"
        and ops_res["unreleased_reserved_articles"] == 0
        and len(ops_res["active_non_terminal_waves"]) == 0
    )
    concurrency_ok = concurrency_res["errors_count"] == 0
    wal_ok = busy == 0 and post_wal_size == 0 and integrity == "ok"

    print("\n" + "=" * 80)
    if ops_ok and concurrency_ok and wal_ok:
        print(" 🏆 FINAL CHALLENGER VERDICT: APPROVE")
        print(" All concurrency, reservation queue, and integrity checks PASSED without failure.")
        sys.exit(0)
    else:
        print(" ❌ FINAL CHALLENGER VERDICT: REQUEST_CHANGES")
        if not ops_ok:
            print("  - ops.db has integrity failure or unreleased reserved articles!")
        if not concurrency_ok:
            print("  - monocle.db failed under concurrent read stress!")
        if not wal_ok:
            print(f"  - monocle.db WAL checkpoint failed (busy={busy}, size={post_wal_size}) or integrity={integrity}!")
        sys.exit(1)


if __name__ == "__main__":
    main()
