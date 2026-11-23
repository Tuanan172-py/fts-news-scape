"""Empirical challenger verification harness for wave W_BKL_01_11021118 database concurrency and integrity."""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET_WAVE = "W_BKL_01_11021118"


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


def test_verify_ops_queue_cli_unblocked() -> None:
    """Verify that verify_ops_queue CLI exits 0 and reports zero reserved articles."""
    script_path = PROJECT_ROOT / "scripts" / "maintenance" / "verify_ops_queue.py"
    proc = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(PROJECT_ROOT),
        env=clean_ops_env(),
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"verify_ops_queue failed:\n{proc.stderr}"
    assert "Unreleased reserved articles (SQL): 0" in proc.stdout
    assert "Store reserved_article_ids() count : 0" in proc.stdout
    assert "VERDICT: QUEUE UNBLOCKED (0 reserved articles). READY FOR PROCESSING." in proc.stdout


def test_ops_store_reservation_queue_zero_held_in_ops_db() -> None:
    """Verify via clean subprocess that OpsStore returns zero reserved articles."""
    code = (
        "from src.core.stdio import force_utf8_stdio; force_utf8_stdio()\n"
        "from src.ops.config import resolve_paths; from src.ops.store import OpsStore\n"
        "paths = resolve_paths()\n"
        "store = OpsStore(paths.ops_db, log_dir=paths.log_dir)\n"
        "reserved = store.reserved_article_ids()\n"
        "assert len(reserved) == 0, f'Reserved articles count is {len(reserved)}'\n"
        "print('STORE_RESERVED_OK', len(reserved))\n"
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
    assert proc.returncode == 0, f"Query failed:\n{proc.stderr}"
    assert "STORE_RESERVED_OK 0" in proc.stdout


def test_wave_status_marked_done_in_ops_db() -> None:
    """Verify that wave W_BKL_01_11021118 is marked DONE and articles are cataloged."""
    code = (
        "from src.core.stdio import force_utf8_stdio; force_utf8_stdio()\n"
        "import sqlite3; from src.ops.config import resolve_paths\n"
        "from src.ops.store import RELEASED_WAVE_STATUSES\n"
        "paths = resolve_paths()\n"
        "conn = sqlite3.connect(f'file:{paths.ops_db.as_posix()}?mode=ro', uri=True)\n"
        "cur = conn.cursor()\n"
        f"wave = cur.execute('SELECT wave_id, status FROM ops_waves WHERE wave_id=\"{TARGET_WAVE}\"').fetchone()\n"
        "assert wave is not None, 'Wave not found'\n"
        "assert wave[1] == 'DONE', f'Expected DONE, got {wave[1]}'\n"
        f"article_count = cur.execute('SELECT count(*) FROM ops_wave_articles WHERE wave_id=\"{TARGET_WAVE}\"').fetchone()[0]\n"
        "assert article_count == 498, f'Expected 498 articles, got {article_count}'\n"
        "marks = ','.join('?' * len(RELEASED_WAVE_STATUSES))\n"
        f"query = 'SELECT count(*) FROM ops_wave_articles a JOIN ops_waves w ON w.wave_id = a.wave_id WHERE a.wave_id = ? AND w.status NOT IN (' + marks + ')'\n"
        f"unreleased = cur.execute(query, ['{TARGET_WAVE}', *RELEASED_WAVE_STATUSES]).fetchone()[0]\n"
        "assert unreleased == 0, f'Expected 0 unreleased, got {unreleased}'\n"
        "print('WAVE_DONE_OK', wave[0], wave[1], article_count, unreleased)\n"
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
    assert proc.returncode == 0, f"Query failed:\n{proc.stderr}"
    assert f"WAVE_DONE_OK {TARGET_WAVE} DONE 498 0" in proc.stdout


def test_monocle_db_integrity_and_journal_mode(tmp_path: Path) -> None:
    """Verify integrity_check and WAL truncation through audit_and_truncate_wal on a synthetic DB.

    The audit writes (it checkpoints and truncates the WAL), so it never runs on the live
    monocle.db (FACT-tests-must-not-write-operational-db); a WAL-mode copy in tmp_path stands in.
    """
    from scripts.maintenance.audit_m4_m5_integrity import audit_and_truncate_wal

    db = tmp_path / "monocle.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY, title TEXT)")
        conn.executemany("INSERT INTO articles (title) VALUES (?)", [(f"t{i}",) for i in range(200)])
        conn.commit()
    finally:
        conn.close()

    res = audit_and_truncate_wal(db)
    assert res["integrity_check"] == "ok"
    assert res["checkpoint"]["busy"] == 0
    assert res["clean_wal_truncated"] is True
    assert res["wal_size_bytes"] == 0


def test_ops_db_integrity_and_journal_mode() -> None:
    """Verify PRAGMA integrity_check and journal mode on ops.db."""
    code = (
        "from src.core.stdio import force_utf8_stdio; force_utf8_stdio()\n"
        "import sqlite3; from pathlib import Path\n"
        "db = Path(r'C:\\data\\news-scape\\ops.db')\n"
        "assert db.exists(), 'ops.db not found'\n"
        "conn = sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True, timeout=30.0)\n"
        "cur = conn.cursor()\n"
        "ic = cur.execute('PRAGMA integrity_check').fetchone()[0]\n"
        "jm = cur.execute('PRAGMA journal_mode').fetchone()[0]\n"
        "assert ic == 'ok', f'Integrity check failed: {ic}'\n"
        "assert jm.lower() == 'wal', f'Expected wal mode, got {jm}'\n"
        "print('OPS_INTEGRITY_OK', ic, jm)\n"
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
    assert proc.returncode == 0, f"Query failed:\n{proc.stderr}"
    assert "OPS_INTEGRITY_OK ok wal" in proc.stdout


def test_wave_articles_ingested_dod_passed_in_monocle() -> None:
    """Verify that articles in wave W_BKL_01_11021118 satisfy DoD pass requirements."""
    code = (
        "from src.core.stdio import force_utf8_stdio; force_utf8_stdio()\n"
        "import sqlite3; from pathlib import Path\n"
        "from scripts.article_run import wave_article_ids\n"
        f"ids = wave_article_ids('{TARGET_WAVE}')\n"
        "assert len(ids) == 498, f'Expected 498 article IDs, got {len(ids)}'\n"
        "db = Path(r'C:\\data\\news-scape\\monocle.db')\n"
        "conn = sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True, timeout=30.0)\n"
        "cur = conn.cursor()\n"
        "marks = ','.join('?' * len(ids))\n"
        "query = f'SELECT count(*), sum(dod_pass) FROM agent_outputs WHERE article_id IN ({marks})'\n"
        "row = cur.execute(query, ids).fetchone()\n"
        "ingested = row[0] or 0; passed = row[1] or 0\n"
        "assert ingested >= 497, f'Expected at least 497 ingested, got {ingested}'\n"
        "assert passed >= 497 and passed == ingested, f'Expected at least 497 passed matching ingested, got {passed}/{ingested}'\n"
        "print('WAVE_DOD_OK', ingested, passed)\n"
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
    assert proc.returncode == 0, f"Query failed:\n{proc.stderr}"
    assert "WAVE_DOD_OK" in proc.stdout


def test_concurrent_read_stress_under_multi_threading() -> None:
    """Stress test concurrent reader connections to monocle.db and ops.db."""
    code = (
        "from src.core.stdio import force_utf8_stdio; force_utf8_stdio()\n"
        "import sqlite3, concurrent.futures\n"
        "from pathlib import Path\n"
        "monocle_db = Path(r'C:\\data\\news-scape\\monocle.db')\n"
        "ops_db = Path(r'C:\\data\\news-scape\\ops.db')\n"
        "\n"
        "def read_monocle(w_id):\n"
        "    conn = sqlite3.connect(f'file:{monocle_db.as_posix()}?mode=ro', uri=True, timeout=10.0)\n"
        "    try:\n"
        "        cur = conn.cursor()\n"
        "        cur.execute('PRAGMA busy_timeout = 30000')\n"
        "        return cur.execute('SELECT count(*) FROM agent_outputs').fetchone()[0]\n"
        "    finally:\n"
        "        conn.close()\n"
        "\n"
        "def read_ops(w_id):\n"
        "    conn = sqlite3.connect(f'file:{ops_db.as_posix()}?mode=ro', uri=True, timeout=10.0)\n"
        "    try:\n"
        "        cur = conn.cursor()\n"
        "        cur.execute('PRAGMA busy_timeout = 30000')\n"
        "        return cur.execute('SELECT count(*) FROM ops_waves').fetchone()[0]\n"
        "    finally:\n"
        "        conn.close()\n"
        "\n"
        "with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:\n"
        "    monocle_res = list(ex.map(read_monocle, range(20)))\n"
        "    ops_res = list(ex.map(read_ops, range(20)))\n"
        "\n"
        "assert len(set(monocle_res)) == 1, 'Inconsistent monocle counts'\n"
        "assert len(set(ops_res)) == 1, 'Inconsistent ops counts'\n"
        "print('CONCURRENCY_OK', monocle_res[0], ops_res[0])\n"
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
    assert proc.returncode == 0, f"Concurrency test failed:\n{proc.stderr}"
    assert "CONCURRENCY_OK" in proc.stdout
