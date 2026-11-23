"""Empirical challenger verification suite for Milestones M3, M4, and M5.

Verifies:
1. Synthetic invariants:
   - v2-lean compact 8 fields contract enforcement.
   - Database isolation detection logic outside OneDrive/SharePoint.
   - PRAGMA wal_checkpoint(TRUNCATE) clean truncation mechanics on SQLite.
2. Operational CLI subprocess verification:
   - audit_m4_m5_integrity.py on operational wave W_BKL_01_10301528 and monocle.db.
   - db_snapshot.py --check on operational database snapshot monocle_review.db.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from project.scripts.maintenance.audit_m4_m5_integrity import (
    REQUIRED_V2_LEAN_FIELDS,
    DISALLOWED_LEGACY_FIELDS,
    audit_operational_db_path,
    audit_and_truncate_wal,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WAVE_ID = "W_BKL_01_10301528"


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


def test_v2_lean_schema_validation_synthetic_invariants():
    """Verify that the v2-lean validator strictly accepts 8 compact fields and rejects legacy keys."""
    valid_record = {
        "i": "art_123",
        "e": [{"id": "HPG", "name": "Hòa Phát", "group": "TIC"}],
        "s": "Tập đoàn Hòa Phát công bố kết quả sản xuất kinh doanh khả quan.",
        "k": ["Sản lượng thép thô đạt mức cao.", "Thị phần nội địa tiếp tục mở rộng."],
        "im": "Hàm ý dòng tiền doanh nghiệp ổn định và hỗ trợ tích cực cho định giá cổ phiếu HPG.",
        "sn": "pos",
        "ts": "today",
        "c": [0, 2],
    }

    record_keys = set(valid_record.keys())
    assert record_keys == REQUIRED_V2_LEAN_FIELDS
    assert record_keys.isdisjoint(DISALLOWED_LEGACY_FIELDS)

    # Missing field test
    missing_c = dict(valid_record)
    del missing_c["c"]
    assert not REQUIRED_V2_LEAN_FIELDS.issubset(set(missing_c.keys()))

    # Disallowed legacy field test
    legacy_record = dict(valid_record)
    legacy_record["materiality_score"] = 0.85
    assert not set(legacy_record.keys()).isdisjoint(DISALLOWED_LEGACY_FIELDS)


def test_database_path_isolation_synthetic_logic():
    """Verify that path isolation correctly identifies OneDrive/SharePoint paths vs local paths."""
    onedrive_path = Path(r"C:\Users\someone\OneDrive - Corporate\news-scape\monocle.db")
    audit_od = audit_operational_db_path(onedrive_path)
    assert audit_od["isolated_from_onedrive"] is False

    sharepoint_path = Path(r"C:\Users\someone\SharePoint\news-scape\monocle.db")
    audit_sp = audit_operational_db_path(sharepoint_path)
    assert audit_sp["isolated_from_onedrive"] is False

    standard_path = Path(r"C:\data\news-scape\monocle.db")
    audit_std = audit_operational_db_path(standard_path)
    assert audit_std["isolated_from_onedrive"] is True
    assert audit_std["is_standard_path"] is True


def test_wal_checkpoint_truncate_synthetic(tmp_path):
    """Verify that PRAGMA wal_checkpoint(TRUNCATE) resets WAL file size to 0 bytes."""
    test_db = tmp_path / "test_wal.db"
    conn = sqlite3.connect(str(test_db))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE test_items (id INTEGER PRIMARY KEY, val TEXT)")
        for i in range(100):
            conn.execute("INSERT INTO test_items (val) VALUES (?)", (f"value_{i}",))
        conn.commit()

        # Execute checkpoint truncate while database is in WAL mode
        audit = audit_and_truncate_wal(test_db)
        assert audit["integrity_check"] == "ok"
        assert audit["checkpoint"]["busy"] == 0
        assert audit["clean_wal_truncated"] is True
    finally:
        conn.close()


@pytest.mark.production_host
def test_operational_cli_audit_m4_m5():
    """Empirically audit operational monocle.db and wave W_BKL_01_10301528 via audit_m4_m5_integrity.py."""
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "maintenance" / "audit_m4_m5_integrity.py"),
        "--wave",
        WAVE_ID,
        "--json",
        "--read-only",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=clean_ops_env(),
        capture_output=True,
        text=True,
        timeout=180,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"audit_m4_m5_integrity.py failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    report = json.loads(proc.stdout)
    assert report["verdict"] == "APPROVE"
    assert report["wave_id"] == WAVE_ID

    # [1] DB Path Isolation
    db_path_info = report["database_path"]
    assert db_path_info["exists"] is True
    assert db_path_info["isolated_from_onedrive"] is True
    assert db_path_info["is_standard_path"] is True

    # [2] v2-lean 8 compact fields
    v2_info = report["v2_lean_contract"]
    assert v2_info["matched_files"] >= 10
    assert v2_info["valid_v2_lean_records"] >= 490
    assert v2_info["adherence_pct"] == 100.0
    assert v2_info["legacy_fields_count"] == 0

    # [3] DoD Quality Gate
    dod_info = report["dod_quality_gate"]
    assert dod_info["overall_total"] >= 30000
    assert dod_info["overall_rate_pct"] >= 95.0
    wm = dod_info["wave_metrics"]
    assert wm["ingested_count"] >= 490
    assert wm["wave_dod_pass_rate"] >= 95.0

    # [4] Integrity & WAL Checkpoint
    wal_info = report["database_integrity_and_wal"]
    assert wal_info["integrity_check"] == "ok"
    # --read-only: the live WAL is checked, never checkpointed or truncated (US-056).
    assert wal_info["checkpoint"] is None
    assert wal_info["clean_wal_truncated"] is None


@pytest.mark.production_host
def test_operational_cli_db_snapshot_check():
    """Verify that db_snapshot.py --check confirms snapshot readiness and integrity ok.

    `--check` only reads an existing snapshot; when it is missing the script creates one
    under the live data directory, so the test skips instead (US-056).
    """
    snapshot = Path(r"C:\data\news-scape\snapshots\monocle_review.db")
    if not snapshot.exists():
        pytest.skip("no snapshot to check; creating one would write the live data directory")
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "db_snapshot.py"),
        "--check",
        "--out",
        str(snapshot),
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=clean_ops_env(),
        capture_output=True,
        text=True,
        timeout=180,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"db_snapshot.py --check failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "PRAGMA integrity    : ok" in proc.stdout
    assert "VERDICT: SNAPSHOT READY FOR SHAREPOINT PACKAGING" in proc.stdout
