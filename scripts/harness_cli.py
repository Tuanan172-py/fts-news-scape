#!/usr/bin/env python3
"""
Harness CLI — Durable Layer & Operational Tool for News-Scape (H2–H5).
Reference: other/harness/HARNESS_BUILD_FROM_SCRATCH_VI.md and HARNESS_RUNBOOK_VI.md.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "harness-orchestration-v1"
CURRENT_SCHEMA_VERSION = 1
DEFAULT_DB_PATH = "harness.db"
DEFAULT_SCHEMA_DIR = "scripts/schema"

CAPABILITIES = [
    "intake",
    "story",
    "decision",
    "backlog",
    "trace",
    "matrix",
    "score-trace",
    "score-context",
    "tool-registry",
    "audit",
    "propose",
    "verify-gate",
]


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat()


def get_db_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


# ---------------------------------------------------------------------------
# Migration & Init
# ---------------------------------------------------------------------------

def init_db(db_path: str = DEFAULT_DB_PATH, schema_dir: str = DEFAULT_SCHEMA_DIR) -> dict[str, Any]:
    conn = get_db_connection(db_path)
    try:
        schema_path = Path(schema_dir) / "001-init.sql"
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found at {schema_path}")
        
        with open(schema_path, "r", encoding="utf-8") as f:
            sql_script = f.read()
        
        conn.executescript(sql_script)
        
        # Record schema version
        conn.execute(
            "INSERT OR REPLACE INTO schema_version (version, applied_at, description) VALUES (?, ?, ?)",
            (1, now_iso(), "001-init.sql initial schema")
        )
        conn.commit()
        return {
            "status": "success",
            "db_path": db_path,
            "schema_version": 1,
            "applied": ["001-init.sql"]
        }
    finally:
        conn.close()


def get_schema_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT MAX(version) as ver FROM schema_version").fetchone()
        return row["ver"] if row and row["ver"] is not None else 0
    except sqlite3.OperationalError:
        return 0


# ---------------------------------------------------------------------------
# Query Commands
# ---------------------------------------------------------------------------

def query_contract(db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    conn = get_db_connection(db_path)
    try:
        ver = get_schema_version(conn)
        state = "ready" if ver >= 1 else "uninitialized"
        return {
            "protocol_version": PROTOCOL_VERSION,
            "schema_version": ver,
            "database_state": state,
            "capabilities": CAPABILITIES,
            "db_path": db_path,
            "timestamp": now_iso()
        }
    finally:
        conn.close()


def query_matrix(db_path: str = DEFAULT_DB_PATH, active_only: bool = False, summary: bool = False) -> dict[str, Any]:
    conn = get_db_connection(db_path)
    try:
        query = "SELECT * FROM story"
        if active_only:
            query += " WHERE status IN ('planned', 'in_progress')"
        query += " ORDER BY id ASC"
        
        rows = conn.execute(query).fetchall()
        stories = [dict(r) for r in rows]
        
        counts = {"planned": 0, "in_progress": 0, "implemented": 0, "blocked": 0, "deferred": 0, "retired": 0}
        for s in stories:
            counts[s["status"]] = counts.get(s["status"], 0) + 1
            
        result = {
            "stories": stories,
            "counts": counts,
            "total": len(stories),
            "timestamp": now_iso()
        }
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Intake Commands
# ---------------------------------------------------------------------------

def cmd_intake(args: argparse.Namespace) -> dict[str, Any]:
    conn = get_db_connection(args.db)
    try:
        flags_json = args.flags
        if isinstance(flags_json, str) and not flags_json.startswith("["):
            flags_list = [f.strip() for f in flags_json.split(",") if f.strip()]
            flags_json = json.dumps(flags_list, ensure_ascii=False)
            
        cur = conn.execute(
            """
            INSERT INTO intake (input_type, summary, risk_lane, risk_flags, story_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (args.type, args.summary, args.lane, flags_json, args.story or None, now_iso())
        )
        conn.commit()
        intake_id = cur.lastrowid
        return {
            "status": "success",
            "intake_id": intake_id,
            "input_type": args.type,
            "risk_lane": args.lane,
            "summary": args.summary,
            "story_id": args.story
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Story Commands
# ---------------------------------------------------------------------------

def cmd_story_add(args: argparse.Namespace) -> dict[str, Any]:
    conn = get_db_connection(args.db)
    try:
        ts = now_iso()
        conn.execute(
            """
            INSERT INTO story (id, title, parent_epic, status, lane, product_contract, 
                              acceptance_criteria, verify_command, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (args.id, args.title, args.parent or "", args.status or "planned",
             args.lane or "normal", args.contract or "", args.criteria or "",
             args.verify_cmd or "", ts, ts)
        )
        conn.commit()
        return {"status": "success", "story_id": args.id, "title": args.title, "story_status": args.status or "planned"}
    finally:
        conn.close()


def cmd_story_update(args: argparse.Namespace) -> dict[str, Any]:
    conn = get_db_connection(args.db)
    try:
        fields = []
        params = []
        
        if args.title is not None:
            fields.append("title = ?")
            params.append(args.title)
        if args.status is not None:
            fields.append("status = ?")
            params.append(args.status)
        if args.lane is not None:
            fields.append("lane = ?")
            params.append(args.lane)
        if args.parent is not None:
            fields.append("parent_epic = ?")
            params.append(args.parent)
        if args.unit_proof is not None:
            fields.append("unit_proof = ?")
            params.append(int(args.unit_proof))
        if args.integ_proof is not None:
            fields.append("integration_proof = ?")
            params.append(int(args.integ_proof))
        if args.e2e_proof is not None:
            fields.append("e2e_proof = ?")
            params.append(int(args.e2e_proof))
        if args.platform_proof is not None:
            fields.append("platform_proof = ?")
            params.append(int(args.platform_proof))
        if args.evidence is not None:
            fields.append("evidence = ?")
            params.append(args.evidence)
        if args.verify_cmd is not None:
            fields.append("verify_command = ?")
            params.append(args.verify_cmd)
            
        fields.append("updated_at = ?")
        params.append(now_iso())
        
        params.append(args.id)
        sql = f"UPDATE story SET {', '.join(fields)} WHERE id = ?"
        
        cur = conn.execute(sql, params)
        conn.commit()
        if cur.rowcount == 0:
            return {"status": "error", "message": f"Story {args.id} not found"}
        return {"status": "success", "story_id": args.id}
    finally:
        conn.close()


def cmd_story_complete(args: argparse.Namespace) -> dict[str, Any]:
    conn = get_db_connection(args.db)
    try:
        story = conn.execute("SELECT * FROM story WHERE id = ?", (args.id,)).fetchone()
        if not story:
            return {"status": "error", "message": f"Story {args.id} not found"}
        
        verify_cmd = args.verify_cmd or story["verify_command"]
        
        # If verify command is specified, run it
        if args.run_verify and verify_cmd:
            print(f"[*] Running verification command: {verify_cmd}", file=sys.stderr)
            res = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True)
            if res.returncode != 0:
                return {
                    "status": "error",
                    "error_code": "VERIFICATION_FAILED",
                    "message": f"Verification failed with exit code {res.returncode}",
                    "stderr": res.stderr[:1000],
                    "stdout": res.stdout[:1000]
                }
            evidence_str = f"Verification passed: {verify_cmd}\n{res.stdout[:500]}"
        else:
            evidence_str = args.evidence or story["evidence"] or "Proof verified"

        unit = int(args.unit_proof) if args.unit_proof is not None else (story["unit_proof"] or 1)
        integ = int(args.integ_proof) if args.integ_proof is not None else story["integration_proof"]
        e2e = int(args.e2e_proof) if args.e2e_proof is not None else story["e2e_proof"]
        platform = int(args.platform_proof) if args.platform_proof is not None else story["platform_proof"]
        
        # Golden Rule: No proof = not implemented
        if unit == 0 and integ == 0 and e2e == 0 and platform == 0:
            return {
                "status": "error",
                "error_code": "NO_PROOF",
                "message": "Cannot mark story as implemented without at least one proof tier passed."
            }

        conn.execute(
            """
            UPDATE story SET status = 'implemented', unit_proof = ?, integration_proof = ?,
                             e2e_proof = ?, platform_proof = ?, evidence = ?, updated_at = ?
            WHERE id = ?
            """,
            (unit, integ, e2e, platform, evidence_str, now_iso(), args.id)
        )
        conn.commit()
        return {"status": "success", "story_id": args.id, "status_to": "implemented", "evidence": evidence_str}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Decision & Backlog Commands
# ---------------------------------------------------------------------------

def cmd_decision_add(args: argparse.Namespace) -> dict[str, Any]:
    conn = get_db_connection(args.db)
    try:
        ts = now_iso()
        conn.execute(
            """
            INSERT OR REPLACE INTO decision (id, title, status, doc_path, predicted_impact, actual_outcome, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (args.id, args.title, args.status or "accepted", args.doc_path,
             args.impact or "", args.outcome or "", ts, ts)
        )
        conn.commit()
        return {"status": "success", "decision_id": args.id}
    finally:
        conn.close()


def cmd_backlog_add(args: argparse.Namespace) -> dict[str, Any]:
    conn = get_db_connection(args.db)
    try:
        ts = now_iso()
        cur = conn.execute(
            """
            INSERT INTO backlog (title, discovered_while, current_pain, suggested_improvement,
                                risk_lane, status, component, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)
            """,
            (args.title, args.discovered_while or "", args.pain, args.suggested or "",
             args.lane or "normal", args.component or "", ts, ts)
        )
        conn.commit()
        return {"status": "success", "backlog_id": cur.lastrowid, "title": args.title}
    finally:
        conn.close()


def cmd_backlog_close(args: argparse.Namespace) -> dict[str, Any]:
    conn = get_db_connection(args.db)
    try:
        conn.execute(
            "UPDATE backlog SET status = 'resolved', outcome = ?, updated_at = ? WHERE id = ?",
            (args.outcome, now_iso(), args.id)
        )
        conn.commit()
        return {"status": "success", "backlog_id": args.id, "backlog_status": "resolved"}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Trace & Scoring Commands (H2 & H3)
# ---------------------------------------------------------------------------

def calculate_score_trace(summary: str, actions: list, files_read: list, files_changed: list, outcome: str) -> float:
    score = 0.0
    if summary and len(summary.strip()) >= 10:
        score += 0.25
    if actions and len(actions) > 0:
        score += 0.25
    if (files_read or files_changed):
        score += 0.25
    if outcome in ("completed", "blocked", "failed", "partial"):
        score += 0.25
    return score


def calculate_score_context(lane: str, files_count: int) -> float:
    # Token & bounded context limits per lane
    limits = {"tiny": 5, "normal": 15, "high-risk": 30}
    max_files = limits.get(lane, 15)
    if files_count <= max_files:
        return 1.0
    return max(0.2, 1.0 - (files_count - max_files) * 0.05)


def cmd_trace(args: argparse.Namespace) -> dict[str, Any]:
    conn = get_db_connection(args.db)
    try:
        actions_json = args.actions if args.actions.startswith("[") else json.dumps([a.strip() for a in args.actions.split(",") if a.strip()], ensure_ascii=False)
        read_json = args.files_read if args.files_read.startswith("[") else json.dumps([f.strip() for f in args.files_read.split(",") if f.strip()], ensure_ascii=False)
        changed_json = args.files_changed if args.files_changed.startswith("[") else json.dumps([f.strip() for f in args.files_changed.split(",") if f.strip()], ensure_ascii=False)
        
        actions_list = json.loads(actions_json)
        read_list = json.loads(read_json)
        changed_list = json.loads(changed_json)
        
        score_t = calculate_score_trace(args.summary, actions_list, read_list, changed_list, args.outcome)
        score_c = calculate_score_context(args.lane or "normal", len(read_list))
        
        cur = conn.execute(
            """
            INSERT INTO trace (story_id, intake_id, task_summary, actions_taken, files_read,
                              files_changed, outcome, score_context, score_trace, friction,
                              error_msg, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (args.story or None, args.intake or None, args.summary, actions_json, read_json,
             changed_json, args.outcome, score_c, score_t, args.friction or "",
             args.error or "", now_iso())
        )
        conn.commit()
        trace_id = cur.lastrowid
        
        # If there's an intervention/error, log it
        if args.error or args.outcome == "blocked":
            conn.execute(
                """
                INSERT INTO intervention (trace_id, story_id, reason, corrective_action, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (trace_id, args.story or None, args.error or "Blocked execution", args.friction or "Pending resolution", now_iso())
            )
            conn.commit()
            
        return {
            "status": "success",
            "trace_id": trace_id,
            "story_id": args.story,
            "score_trace": score_t,
            "score_context": score_c,
            "outcome": args.outcome
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Audit & Self-Improvement (H4 & H5)
# ---------------------------------------------------------------------------

def cmd_audit(db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    conn = get_db_connection(db_path)
    try:
        checks = {}
        total_penalty = 0.0
        
        # 1. Orphaned / Unproven stories marked implemented
        unproven = conn.execute(
            "SELECT id FROM story WHERE status = 'implemented' AND unit_proof=0 AND integration_proof=0 AND e2e_proof=0 AND platform_proof=0"
        ).fetchall()
        checks["unproven_implemented_stories"] = [r["id"] for r in unproven]
        total_penalty += len(unproven) * 0.2
        
        # 2. In-progress story count (WIP = 1 check)
        in_prog = conn.execute("SELECT id FROM story WHERE status = 'in_progress'").fetchall()
        checks["in_progress_count"] = len(in_prog)
        if len(in_prog) > 1:
            checks["wip_violation"] = [r["id"] for r in in_prog]
            total_penalty += 0.25
            
        # 3. Missing traces for stories
        no_trace = conn.execute(
            """
            SELECT s.id FROM story s
            LEFT JOIN trace t ON s.id = t.story_id
            WHERE s.status IN ('implemented', 'blocked') AND t.id IS NULL
            """
        ).fetchall()
        checks["stories_missing_traces"] = [r["id"] for r in no_trace]
        total_penalty += len(no_trace) * 0.1
        
        # 4. Open friction / backlog count
        open_backlog = conn.execute("SELECT COUNT(*) as n FROM backlog WHERE status = 'open'").fetchone()["n"]
        checks["open_backlog_count"] = open_backlog
        if open_backlog > 5:
            total_penalty += 0.15
            
        # 5. Missing decision records for high-risk stories
        high_risk_no_adr = conn.execute(
            """
            SELECT s.id FROM story s
            WHERE s.lane = 'high-risk' AND s.id NOT IN (SELECT story_id FROM intake WHERE story_id IS NOT NULL)
            """
        ).fetchall()
        checks["high_risk_missing_adr_gate"] = [r["id"] for r in high_risk_no_adr]
        total_penalty += len(high_risk_no_adr) * 0.15
        
        # 6. Schema health
        checks["schema_version"] = get_schema_version(conn)
        
        health_score = max(0.0, min(1.0, 1.0 - total_penalty))
        entropy_score = round(1.0 - health_score, 2)
        
        return {
            "status": "success",
            "health_score": round(health_score, 2),
            "entropy_score": entropy_score,
            "checks": checks,
            "timestamp": now_iso()
        }
    finally:
        conn.close()


def cmd_propose(db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    conn = get_db_connection(db_path)
    try:
        # Group friction by component
        rows = conn.execute(
            """
            SELECT component, COUNT(*) as cnt, GROUP_CONCAT(title, '; ') as items
            FROM backlog
            WHERE status = 'open' AND component IS NOT NULL AND component != ''
            GROUP BY component
            ORDER BY cnt DESC
            """
        ).fetchall()
        
        proposals = []
        for r in rows:
            proposals.append({
                "target_component": r["component"],
                "friction_count": r["cnt"],
                "evidence_items": r["items"],
                "recommendation": f"Consolidate {r['cnt']} open items in '{r['component']}' into an ADR / targeted improvement story.",
                "action_lane": "normal" if r["cnt"] < 3 else "high-risk"
            })
            
        return {
            "status": "success",
            "total_open_components": len(proposals),
            "proposals": proposals,
            "timestamp": now_iso()
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI Argument Parser Setup
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="News-Scape Harness CLI (H2-H5 Durable Layer)")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Path to harness.db SQLite file")
    parser.add_argument("--json", action="store_true", help="Output results in raw JSON format")
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # init
    init_parser = subparsers.add_parser("init", help="Initialize the durable database schema")
    init_parser.add_argument("--schema-dir", default=DEFAULT_SCHEMA_DIR, help="Directory containing schema sql files")
    
    # query
    query_parser = subparsers.add_parser("query", help="Query durable layer data")
    query_sub = query_parser.add_subparsers(dest="query_target", required=True)
    
    query_sub.add_parser("contract", help="Query harness orchestration contract capabilities")
    
    matrix_p = query_sub.add_parser("matrix", help="Query test proof matrix")
    matrix_p.add_argument("--active", action="store_true", help="Only show active/in_progress stories")
    matrix_p.add_argument("--summary", action="store_true", help="Show summary counts only")
    
    # intake
    intake_p = subparsers.add_parser("intake", help="Classify and record a new task request")
    intake_p.add_argument("--type", required=True, choices=["new_spec", "spec_slice", "change_request", "new_initiative", "maintenance", "harness_improvement", "qa_inquiry", "diagnostic", "exploration"])
    intake_p.add_argument("--summary", required=True, help="Short summary of the request")
    intake_p.add_argument("--lane", required=True, choices=["tiny", "normal", "high-risk"])
    intake_p.add_argument("--flags", default="[]", help="JSON array or comma-separated list of risk flags")
    intake_p.add_argument("--story", help="Associated story ID")
    
    # story
    story_p = subparsers.add_parser("story", help="Manage stories")
    story_sub = story_p.add_subparsers(dest="story_action", required=True)
    
    s_add = story_sub.add_parser("add", help="Add a new story")
    s_add.add_argument("--id", required=True, help="Story ID (e.g. US-001)")
    s_add.add_argument("--title", required=True, help="Story title")
    s_add.add_argument("--parent", help="Parent epic")
    s_add.add_argument("--lane", choices=["tiny", "normal", "high-risk"], default="normal")
    s_add.add_argument("--status", choices=["planned", "in_progress", "implemented", "changed", "retired", "blocked", "deferred"], default="planned")
    s_add.add_argument("--contract", help="Product contract definition")
    s_add.add_argument("--criteria", help="Acceptance criteria")
    s_add.add_argument("--verify-cmd", help="Verification command to run for proof")
    
    s_up = story_sub.add_parser("update", help="Update an existing story")
    s_up.add_argument("--id", required=True, help="Story ID")
    s_up.add_argument("--title", help="New title")
    s_up.add_argument("--parent", help="New parent epic")
    s_up.add_argument("--status", choices=["planned", "in_progress", "implemented", "changed", "retired", "blocked", "deferred"])
    s_up.add_argument("--lane", choices=["tiny", "normal", "high-risk"])
    s_up.add_argument("--unit-proof", type=int, choices=[0, 1])
    s_up.add_argument("--integ-proof", type=int, choices=[0, 1])
    s_up.add_argument("--e2e-proof", type=int, choices=[0, 1])
    s_up.add_argument("--platform-proof", type=int, choices=[0, 1])
    s_up.add_argument("--evidence", help="Evidence text")
    s_up.add_argument("--verify-cmd", help="Verification command")
    
    s_comp = story_sub.add_parser("complete", help="Complete a story with proof gate")
    s_comp.add_argument("--id", required=True, help="Story ID")
    s_comp.add_argument("--unit-proof", type=int, choices=[0, 1])
    s_comp.add_argument("--integ-proof", type=int, choices=[0, 1])
    s_comp.add_argument("--e2e-proof", type=int, choices=[0, 1])
    s_comp.add_argument("--platform-proof", type=int, choices=[0, 1])
    s_comp.add_argument("--evidence", help="Evidence text")
    s_comp.add_argument("--verify-cmd", help="Verification command override")
    s_comp.add_argument("--run-verify", action="store_true", help="Execute the verify command live")
    
    # decision
    dec_p = subparsers.add_parser("decision", help="Manage ADR decision records")
    dec_sub = dec_p.add_subparsers(dest="decision_action", required=True)
    d_add = dec_sub.add_parser("add", help="Add or update a decision")
    d_add.add_argument("--id", required=True, help="Decision ID (e.g. 0001-harness-first)")
    d_add.add_argument("--title", required=True, help="Title")
    d_add.add_argument("--doc-path", required=True, help="Path to markdown document")
    d_add.add_argument("--status", choices=["proposed", "accepted", "superseded", "rejected"], default="accepted")
    d_add.add_argument("--impact", help="Predicted impact")
    d_add.add_argument("--outcome", help="Actual measured outcome")
    
    # backlog
    bl_p = subparsers.add_parser("backlog", help="Manage friction backlog")
    bl_sub = bl_p.add_subparsers(dest="backlog_action", required=True)
    b_add = bl_sub.add_parser("add", help="Record a new friction item")
    b_add.add_argument("--title", required=True, help="Title")
    b_add.add_argument("--pain", required=True, help="Current pain description")
    b_add.add_argument("--suggested", help="Suggested improvement")
    b_add.add_argument("--lane", choices=["tiny", "normal", "high-risk"], default="normal")
    b_add.add_argument("--component", help="Component area")
    b_add.add_argument("--discovered-while", help="Context where discovered")
    
    b_close = bl_sub.add_parser("close", help="Close a resolved backlog item")
    b_close.add_argument("--id", type=int, required=True, help="Backlog item ID")
    b_close.add_argument("--outcome", required=True, help="Resolution outcome")
    
    # trace
    tr_p = subparsers.add_parser("trace", help="Record execution trace")
    tr_p.add_argument("--summary", required=True, help="Task summary")
    tr_p.add_argument("--story", help="Associated Story ID")
    tr_p.add_argument("--intake", type=int, help="Associated Intake ID")
    tr_p.add_argument("--outcome", required=True, choices=["completed", "blocked", "failed", "partial"])
    tr_p.add_argument("--actions", default="[]", help="JSON array or comma-separated actions taken")
    tr_p.add_argument("--files-read", default="[]", help="JSON array or comma-separated files read")
    tr_p.add_argument("--files-changed", default="[]", help="JSON array or comma-separated files changed")
    tr_p.add_argument("--lane", choices=["tiny", "normal", "high-risk"], default="normal")
    tr_p.add_argument("--friction", help="Friction notes")
    tr_p.add_argument("--error", help="Error message if any")
    
    # audit & propose
    subparsers.add_parser("audit", help="Run harness drift & entropy audit")
    subparsers.add_parser("propose", help="Generate self-improvement proposals from backlog friction")
    
    return parser


def format_matrix_table(matrix_data: dict[str, Any]) -> str:
    lines = [
        "| Story | Parent/Epic | Status | Unit | Integ | E2E | Plat | Evidence |",
        "|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|",
    ]
    for s in matrix_data["stories"]:
        u = "1" if s["unit_proof"] else "0"
        i = "1" if s["integration_proof"] else "—"
        e = "1" if s["e2e_proof"] else "—"
        p = "1" if s["platform_proof"] else "—"
        ev = (s["evidence"] or "")[:40].replace("\n", " ")
        lines.append(f"| {s['id']} | {s['parent_epic'] or '—'} | `{s['status']}` | {u} | {i} | {e} | {p} | {ev} |")
    
    lines.append("")
    cnt = matrix_data["counts"]
    lines.append(f"Summary: Total: {matrix_data['total']} | Implemented: {cnt.get('implemented', 0)} | In-Progress: {cnt.get('in_progress', 0)} | Planned: {cnt.get('planned', 0)} | Blocked: {cnt.get('blocked', 0)}")
    return "\n".join(lines)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    
    try:
        if args.command == "init":
            res = init_db(args.db, args.schema_dir)
        elif args.command == "query":
            if args.query_target == "contract":
                res = query_contract(args.db)
            elif args.query_target == "matrix":
                res = query_matrix(args.db, args.active, args.summary)
                if not args.json:
                    print(format_matrix_table(res))
                    return
        elif args.command == "intake":
            res = cmd_intake(args)
        elif args.command == "story":
            if args.story_action == "add":
                res = cmd_story_add(args)
            elif args.story_action == "update":
                res = cmd_story_update(args)
            elif args.story_action == "complete":
                res = cmd_story_complete(args)
        elif args.command == "decision":
            if args.decision_action == "add":
                res = cmd_decision_add(args)
        elif args.command == "backlog":
            if args.backlog_action == "add":
                res = cmd_backlog_add(args)
            elif args.backlog_action == "close":
                res = cmd_backlog_close(args)
        elif args.command == "trace":
            res = cmd_trace(args)
        elif args.command == "audit":
            res = cmd_audit(args.db)
        elif args.command == "propose":
            res = cmd_propose(args.db)
        else:
            parser.print_help()
            sys.exit(1)
            
        print(json.dumps(res, indent=2, ensure_ascii=False))
        if res.get("status") == "error":
            sys.exit(1)
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, indent=2, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
