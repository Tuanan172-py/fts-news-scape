"""Audit Milestone 4 DoD Quality Gate and Milestone 5 Database Integrity."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core import paths
from src.core.config import resolve_db_path
from src.core.stdio import force_utf8_stdio
from scripts.article_run import wave_article_ids

force_utf8_stdio()

REQUIRED_V2_LEAN_FIELDS = {"i", "e", "s", "k", "im", "sn", "ts", "c"}
DISALLOWED_LEGACY_FIELDS = {"materiality", "materiality_score", "event_type", "impact_area"}


def audit_operational_db_path(db_file: Path) -> dict[str, Any]:
    """Verify that the database path is strictly isolated outside OneDrive.

    Args:
        db_file: Path to operational monocle.db SQLite file.

    Returns:
        Audit dictionary with path validation results.
    """
    resolved = db_file.resolve()
    path_str = str(resolved).lower()
    in_onedrive = "onedrive" in path_str or "sharepoint" in path_str
    is_standard_path = resolved == Path(r"C:\data\news-scape\monocle.db")

    return {
        "path": str(resolved),
        "exists": resolved.is_file(),
        "is_standard_path": is_standard_path,
        "isolated_from_onedrive": not in_onedrive,
        "valid": resolved.is_file() and not in_onedrive,
    }


def audit_v2_lean_json_packets(wave_id: str) -> dict[str, Any]:
    """Verify 100% adherence to v2-lean 8 compact fields across model outputs.

    Args:
        wave_id: Identifier of the wave to inspect.

    Returns:
        Audit dictionary with field conformance metrics.
    """
    outputs_dir = paths.agent_outputs_dir("_article")
    pattern = f"article_{wave_id}_*.output.json"
    matched_files = sorted(outputs_dir.glob(pattern))

    total_records = 0
    valid_records = 0
    missing_fields_count = 0
    legacy_fields_count = 0
    field_frequencies: dict[str, int] = {}

    for file_path in matched_files:
        try:
            records = json.loads(file_path.read_text(encoding="utf-8"))
            if not isinstance(records, list):
                continue
            for item in records:
                if not isinstance(item, dict):
                    continue
                total_records += 1
                keys = set(item.keys())
                for k in keys:
                    field_frequencies[k] = field_frequencies.get(k, 0) + 1

                has_all_required = REQUIRED_V2_LEAN_FIELDS.issubset(keys)
                has_no_legacy = keys.isdisjoint(DISALLOWED_LEGACY_FIELDS)

                if has_all_required and has_no_legacy and keys == REQUIRED_V2_LEAN_FIELDS:
                    valid_records += 1
                else:
                    if not has_all_required:
                        missing_fields_count += 1
                    if not has_no_legacy:
                        legacy_fields_count += 1
        except Exception:
            continue

    return {
        "wave_id": wave_id,
        "matched_files": len(matched_files),
        "total_records": total_records,
        "valid_v2_lean_records": valid_records,
        "missing_fields_count": missing_fields_count,
        "legacy_fields_count": legacy_fields_count,
        "adherence_pct": (valid_records / total_records * 100.0) if total_records > 0 else 0.0,
        "field_frequencies": field_frequencies,
    }


def audit_agent_outputs_table(db_file: Path, wave_id: str | None = None) -> dict[str, Any]:
    """Audit the agent_outputs table for DoD compliance and newly ingested records.

    Args:
        db_file: Path to operational monocle.db SQLite file.
        wave_id: Identifier of wave to check specifically.

    Returns:
        Audit dictionary with database metrics and DoD pass rates.
    """
    uri = f"file:{db_file.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    try:
        c = conn.cursor()

        # Overall DoD metrics
        overall_total = c.execute("SELECT count(*) FROM agent_outputs").fetchone()[0]
        overall_pass = c.execute("SELECT count(*) FROM agent_outputs WHERE dod_pass = 1").fetchone()[0]
        overall_rate = (overall_pass / overall_total * 100.0) if overall_total > 0 else 0.0

        wave_metrics = {}
        if wave_id:
            article_ids = wave_article_ids(wave_id)
            if article_ids:
                marks = ",".join("?" * len(article_ids))
                query = (
                    f"SELECT count(*), sum(dod_pass) "
                    f"FROM agent_outputs WHERE article_id IN ({marks})"
                )
                row = c.execute(query, article_ids).fetchone()
                w_count = row[0] or 0
                w_pass = row[1] or 0
                w_rate = (w_pass / w_count * 100.0) if w_count > 0 else 0.0
                wave_metrics = {
                    "wave_id": wave_id,
                    "target_articles": len(article_ids),
                    "ingested_count": w_count,
                    "dod_pass_count": w_pass,
                    "wave_dod_pass_rate": w_rate,
                }

        # Check required schema columns in agent_outputs
        cols_info = c.execute("PRAGMA table_info(agent_outputs)").fetchall()
        col_names = [col[1] for col in cols_info]

        return {
            "overall_total": overall_total,
            "overall_pass": overall_pass,
            "overall_rate_pct": overall_rate,
            "columns": col_names,
            "wave_metrics": wave_metrics,
        }
    finally:
        conn.close()


def audit_and_truncate_wal(db_file: Path) -> dict[str, Any]:
    """Run PRAGMA integrity_check and PRAGMA wal_checkpoint(TRUNCATE).

    Args:
        db_file: Path to operational monocle.db SQLite file.

    Returns:
        Audit dictionary with PRAGMA results and WAL file sizes.
    """
    # Open read-write connection to run integrity_check and wal_checkpoint
    conn = sqlite3.connect(str(db_file), timeout=60.0)
    try:
        c = conn.cursor()
        c.execute("PRAGMA busy_timeout = 60000")
        integrity_result = c.execute("PRAGMA integrity_check").fetchone()[0]

        # Stage 1: Flush dirty pages into DB
        c.execute("PRAGMA wal_checkpoint(RESTART)")

        # Stage 2: Truncate WAL to 0 bytes with 10-attempt retry loop
        busy = 1
        log_pages = checkpointed_pages = -1
        for _ in range(10):
            res = c.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            busy, log_pages, checkpointed_pages = res
            if busy == 0:
                break
            time.sleep(1.0)
    finally:
        conn.close()

    wal_file = db_file.parent / f"{db_file.name}-wal"
    shm_file = db_file.parent / f"{db_file.name}-shm"

    wal_size = wal_file.stat().st_size if wal_file.exists() else 0
    shm_size = shm_file.stat().st_size if shm_file.exists() else 0

    return {
        "integrity_check": integrity_result,
        "checkpoint": {
            "busy": busy,
            "log_pages": log_pages,
            "checkpointed_pages": checkpointed_pages,
        },
        "wal_file_exists": wal_file.exists(),
        "wal_size_bytes": wal_size,
        "shm_file_exists": shm_file.exists(),
        "shm_size_bytes": shm_size,
        "clean_wal_truncated": wal_size == 0,
    }


def audit_integrity_readonly(db_file: Path) -> dict[str, Any]:
    """Run PRAGMA integrity_check on a read-only connection, without any checkpoint.

    The read-only counterpart of `audit_and_truncate_wal` for checks against a live
    database: it never writes, so the WAL is reported as found, not truncated.

    Args:
        db_file: Path to the SQLite file.

    Returns:
        Audit dictionary shaped like `audit_and_truncate_wal`, with `checkpoint` None
        and `clean_wal_truncated` None.
    """
    conn = sqlite3.connect(f"file:{db_file.as_posix()}?mode=ro", uri=True, timeout=60.0)
    try:
        integrity_result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()
    wal_file = db_file.parent / f"{db_file.name}-wal"
    shm_file = db_file.parent / f"{db_file.name}-shm"
    return {
        "integrity_check": integrity_result,
        "checkpoint": None,
        "wal_file_exists": wal_file.exists(),
        "wal_size_bytes": wal_file.stat().st_size if wal_file.exists() else 0,
        "shm_file_exists": shm_file.exists(),
        "shm_size_bytes": shm_file.stat().st_size if shm_file.exists() else 0,
        "clean_wal_truncated": None,
    }


def run_full_audit(wave_id: str = "W_BKL_01_10301528", *, as_json: bool = False,
                   read_only: bool = False) -> tuple[bool, dict[str, Any]]:
    """Run full audit for Milestones 4 and 5 and print forensic report.

    Args:
        wave_id: Identifier of wave to audit.
        as_json: If True, suppress prose and print JSON output only.
        read_only: If True, check integrity without checkpointing or truncating the WAL,
            so the audit is safe against a live database.

    Returns:
        Tuple of (success boolean, report dictionary).
    """
    db_file = resolve_db_path()

    # 1. Operational DB Path Isolation
    path_audit = audit_operational_db_path(db_file)

    # 2. v2-lean 8 Compact Fields Adherence
    v2_audit = audit_v2_lean_json_packets(wave_id)

    # 3. DoD Quality Gate in agent_outputs
    db_audit = audit_agent_outputs_table(db_file, wave_id)

    # 4. PRAGMA integrity_check, then wal_checkpoint(TRUNCATE) unless read-only
    wal_audit = audit_integrity_readonly(db_file) if read_only else audit_and_truncate_wal(db_file)
    wal_ok = wal_audit["integrity_check"] == "ok" and (
        read_only or (wal_audit["checkpoint"]["busy"] == 0 and wal_audit["clean_wal_truncated"]))

    success = (
        path_audit["valid"]
        and v2_audit["adherence_pct"] == 100.0
        and db_audit["overall_rate_pct"] >= 95.0
        and (not db_audit.get("wave_metrics") or db_audit["wave_metrics"]["wave_dod_pass_rate"] >= 95.0)
        and wal_ok
    )

    report = {
        "verdict": "APPROVE" if success else "REJECT",
        "wave_id": wave_id,
        "database_path": path_audit,
        "v2_lean_contract": v2_audit,
        "dod_quality_gate": db_audit,
        "database_integrity_and_wal": wal_audit,
    }

    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return success, report

    print("=" * 80)
    print(" EMPIRICAL AUDIT REPORT: MILESTONES M4 & M5 FORENSIC VERIFICATION")
    print("=" * 80)

    print("\n[1] OPERATIONAL DATABASE PATH ISOLATION (RULE 03 & ADR 0021)")
    print(f"  Path                  : {path_audit['path']}")
    print(f"  Exists                : {path_audit['exists']}")
    print(f"  Standard Path Match   : {path_audit['is_standard_path']}")
    print(f"  Isolated From OneDrive: {path_audit['isolated_from_onedrive']}")

    print(f"\n[2] V2-LEAN 8 COMPACT FIELDS CONTRACT ({wave_id})")
    print(f"  Matched output files  : {v2_audit['matched_files']}")
    print(f"  Total records audited : {v2_audit['total_records']}")
    print(f"  Valid v2-lean records : {v2_audit['valid_v2_lean_records']}")
    print(f"  Adherence Percentage  : {v2_audit['adherence_pct']:.2f}%")
    print(f"  Disallowed/Legacy Keys: {v2_audit['legacy_fields_count']}")
    print(f"  Field Frequencies     : {v2_audit['field_frequencies']}")

    print("\n[3] DEFINITION-OF-DONE (DOD) QUALITY GATE IN MONOCLE.DB")
    print(f"  Total agent_outputs   : {db_audit['overall_total']:,}")
    print(f"  Passed DoD (dod_pass=1: {db_audit['overall_pass']:,}")
    print(f"  Overall DoD Pass Rate : {db_audit['overall_rate_pct']:.2f}% (Threshold >= 95.0%)")
    if db_audit.get("wave_metrics"):
        wm = db_audit["wave_metrics"]
        print(f"  Wave {wave_id} Ingested : {wm['ingested_count']}/{wm['target_articles']}")
        print(f"  Wave DoD Pass Count   : {wm['dod_pass_count']}")
        print(f"  Wave DoD Pass Rate    : {wm['wave_dod_pass_rate']:.2f}%")

    print("\n[4] DATABASE INTEGRITY & WAL TRUNCATE CHECKPOINT")
    print(f"  PRAGMA integrity_check: {wal_audit['integrity_check']}")
    cp = wal_audit["checkpoint"]
    if cp is None:
        print("  Checkpoint            : skipped (read-only)")
    else:
        print(f"  Checkpoint busy status: {cp['busy']} (0 = no lock contention)")
        print(f"  Log pages / checkpntd : {cp['log_pages']} / {cp['checkpointed_pages']}")
    print(f"  WAL file size         : {wal_audit['wal_size_bytes']} bytes (Truncated = {wal_audit['clean_wal_truncated']})")
    print(f"  SHM file size         : {wal_audit['shm_size_bytes']} bytes")

    print("\n" + "=" * 80)
    if success:
        print(" VERDICT: ALL FORENSIC CHECKS PASSED (100% OK, READY FOR SHAREPOINT)")
    else:
        print(" VERDICT: INTEGRITY CHECKS FAILED")
    print("=" * 80 + "\n")

    return success, report


def main() -> None:
    """Parse arguments and execute audit."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wave", default="W_BKL_01_10301528", help="Wave ID to audit")
    parser.add_argument("--json", action="store_true", help="Print output in JSON format")
    parser.add_argument("--read-only", action="store_true",
                        help="Check integrity without checkpointing or truncating the WAL")
    args = parser.parse_args()
    success, _ = run_full_audit(args.wave, as_json=args.json, read_only=args.read_only)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
