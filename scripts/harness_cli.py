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
CURRENT_SCHEMA_VERSION = 4
DEFAULT_DB_PATH = "harness.db"
DEFAULT_SCHEMA_DIR = "scripts/schema"

CAPABILITIES = [
    "intake",
    "story",
    "decision",
    "backlog",
    "trace",
    "metric",
    "matrix",
    "agent-metrics",
    "score-trace",
    "score-context",
    "tool-registry",
    "audit",
    "propose",
    "verify-gate",
    "codebase-audit",
    "git-lifecycle",
    "knowledge-docs",
]


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat()


def get_git_branch() -> str | None:
    try:
        res = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True)
        return res.stdout.strip() or None
    except Exception:
        return None


def get_git_head_commit() -> str | None:
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        return res.stdout.strip() or None
    except Exception:
        return None


def is_git_working_tree_dirty() -> bool:
    try:
        res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True)
        return bool(res.stdout.strip())
    except Exception:
        return False


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
    """Áp dụng tuần tự mọi tệp migration `NNN-*.sql` theo thứ tự số phiên bản.

    Args:
        db_path: Đường dẫn tệp SQLite harness.
        schema_dir: Thư mục chứa các tệp migration.

    Returns:
        Từ điển trạng thái gồm phiên bản schema hiện tại và danh sách tệp đã áp dụng.

    Raises:
        FileNotFoundError: Khi thư mục schema không có tệp migration nào.
    """
    conn = get_db_connection(db_path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT, description TEXT);")
        cur = conn.execute("SELECT version FROM schema_version")
        applied_versions = {row["version"] for row in cur.fetchall()}

        migrations = sorted(Path(schema_dir).glob("[0-9][0-9][0-9]-*.sql"))
        if not migrations:
            raise FileNotFoundError(f"No migration files found in {schema_dir}")

        applied: list[str] = []
        max_version = max(applied_versions) if applied_versions else 0
        for path in migrations:
            version = int(path.name[:3])
            if version in applied_versions:
                continue
            with open(path, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
            conn.execute(
                "INSERT OR REPLACE INTO schema_version (version, applied_at, description) VALUES (?, ?, ?)",
                (version, now_iso(), path.name),
            )
            applied.append(path.name)
            max_version = max(max_version, version)

        conn.commit()
        return {
            "status": "success",
            "db_path": db_path,
            "schema_version": max_version,
            "applied": applied,
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

        git_commit = get_git_head_commit()
        git_branch = get_git_branch()
        commit_result = None
        if getattr(args, "commit", False):
            if is_git_working_tree_dirty():
                title = story["title"] or args.id
                c_type = "feat"
                if any(w in title.lower() for w in ["fix", "sửa", "chữa"]):
                    c_type = "fix"
                elif any(w in title.lower() for w in ["refactor", "tái cấu trúc", "chuẩn hóa"]):
                    c_type = "refactor"
                elif any(w in title.lower() for w in ["doc", "tài liệu"]):
                    c_type = "docs"
                commit_msg = f"{c_type}({args.id.lower()}): {title} ({args.id})"
                subprocess.run(["git", "add", "-u"], capture_output=True, text=True)
                res_cmt = subprocess.run(["git", "commit", "-m", commit_msg], capture_output=True, text=True)
                if res_cmt.returncode == 0:
                    git_commit = get_git_head_commit()
                    commit_result = {"status": "committed", "commit": git_commit, "message": commit_msg}
                else:
                    commit_result = {"status": "commit_failed", "stderr": res_cmt.stderr.strip()}

        conn.execute(
            """
            UPDATE story SET status = 'implemented', unit_proof = ?, integration_proof = ?,
                             e2e_proof = ?, platform_proof = ?, evidence = ?,
                             git_commit = ?, git_branch = ?, updated_at = ?
            WHERE id = ?
            """,
            (unit, integ, e2e, platform, evidence_str, git_commit, git_branch, now_iso(), args.id)
        )
        conn.commit()
        ret = {
            "status": "success",
            "story_id": args.id,
            "status_to": "implemented",
            "evidence": evidence_str,
            "git_commit": git_commit,
            "git_branch": git_branch,
        }
        if commit_result:
            ret["commit_result"] = commit_result
        return ret
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
        
        git_commit = get_git_head_commit()
        git_branch = get_git_branch()
        cur = conn.execute(
            """
            INSERT INTO trace (story_id, intake_id, task_summary, actions_taken, files_read,
                              files_changed, outcome, score_context, score_trace, friction,
                              error_msg, git_commit, git_branch, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (args.story or None, args.intake or None, args.summary, actions_json, read_json,
             changed_json, args.outcome, score_c, score_t, args.friction or "",
             args.error or "", git_commit, git_branch, now_iso())
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
            "outcome": args.outcome,
            "git_commit": git_commit,
            "git_branch": git_branch,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Audit & Self-Improvement (H4 & H5)
# ---------------------------------------------------------------------------

def cmd_audit(db_path: str = DEFAULT_DB_PATH, check_codebase: bool = False) -> dict[str, Any]:
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
        # WIP=1 per worktree (ADR-0022): count by the branch each story file declares.
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import knowledge

            docs = [d for d in knowledge.discover(knowledge.REPO_ROOT) if d.has_frontmatter]
            by_branch = knowledge.wip_by_branch(docs)
            attributed = {sid for ids in by_branch.values() for sid in ids}
            crowded = {b: ids for b, ids in by_branch.items() if len(ids) > 1}
            if crowded:
                checks["wip_violation"] = crowded
                total_penalty += 0.25
            checks["wip_unattributed"] = [r["id"] for r in in_prog if r["id"] not in attributed]
        except Exception as e:
            checks["wip_check_error"] = str(e)
            
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

        # 6b. Knowledge document contract (ADR-0021)
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import knowledge

            k_findings = knowledge.lint(knowledge.REPO_ROOT)
            checks["knowledge_contract_findings"] = [str(f) for f in k_findings]
            checks["knowledge_unmigrated"] = len(knowledge.legacy_files(knowledge.load_legacy(knowledge.REPO_ROOT)))
            total_penalty += min(0.3, len(k_findings) * 0.02)
        except Exception as e:
            checks["knowledge_contract_error"] = str(e)

        # 7. Codebase & Git hygiene
        if check_codebase:
            try:
                import importlib.util
                repo_root = Path(db_path).resolve().parent
                audit_script = repo_root / "project" / "scripts" / "maintenance" / "audit_codebase.py"
                if not audit_script.exists():
                    cli_repo_root = Path(__file__).resolve().parent.parent
                    audit_script = cli_repo_root / "project" / "scripts" / "maintenance" / "audit_codebase.py"
                    if audit_script.exists():
                        repo_root = cli_repo_root
                
                if audit_script.exists():
                    spec = importlib.util.spec_from_file_location("audit_codebase_module", str(audit_script))
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        cb_res = mod.run_full_audit(repo_root)
                        checks["codebase_hygiene"] = cb_res["results"]
                        conflicts = cb_res["results"].get("OneDrive Conflict Files", {})
                        if conflicts.get("status") == "FAIL":
                            total_penalty += 0.15
                        ast_res = cb_res["results"].get("Python AST Syntax", {})
                        if ast_res.get("status") == "FAIL":
                            total_penalty += 0.25
                        tracked_res = cb_res["results"].get("Tracked Files Sanity", {})
                        if tracked_res.get("status") == "FAIL":
                            total_penalty += 0.20
                else:
                    checks["codebase_hygiene_warning"] = f"Script audit not found at {audit_script}"
            except Exception as e:
                checks["codebase_hygiene_error"] = str(e)
        
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

        agent_proposals = _propose_from_agent_metrics(conn)

        return {
            "status": "success",
            "total_open_components": len(proposals),
            "proposals": proposals,
            "agent_metric_proposals": agent_proposals,
            "timestamp": now_iso()
        }
    finally:
        conn.close()


def _propose_from_agent_metrics(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Sinh đề xuất cải tiến từ xu hướng KPI của từng cognitive agent (Spine 3).

    Args:
        conn: Kết nối harness.db đang mở.

    Returns:
        Danh sách đề xuất, mỗi phần tử nêu agent, triệu chứng và hành động khuyến nghị.
    """
    try:
        rows = conn.execute(
            """
            SELECT agent_id,
                   SUM(dod_pass) AS pass, SUM(dod_total) AS total,
                   SUM(fp_flags) AS fp, SUM(items) AS items, COUNT(*) AS runs
            FROM agent_metrics
            GROUP BY agent_id
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return []                       # schema chưa nâng lên v2

    out: list[dict[str, Any]] = []
    for r in rows:
        total = r["total"] or 0
        rate = (r["pass"] / total) if total else 1.0
        symptoms = []
        if total and rate < 0.95:
            symptoms.append(f"dod_pass_rate={rate:.0%} (<95%)")
        if (r["fp"] or 0) > 0:
            symptoms.append(f"fp_flags={r['fp']}")
        if not symptoms:
            continue
        out.append({
            "agent_id": r["agent_id"],
            "runs": r["runs"],
            "items": r["items"],
            "symptoms": symptoms,
            "recommendation": (
                f"Rà soát SKILL của '{r['agent_id']}' + siết điều khoản DoD tương ứng; "
                f"lập backlog/ADR nếu tái diễn."
            ),
            "action_lane": "normal" if rate >= 0.85 and (r["fp"] or 0) < 3 else "high-risk",
        })
    return out


# ---------------------------------------------------------------------------
# Agent Metrics Commands (Spine 3 — Per-Agent KPI Ledger)
# ---------------------------------------------------------------------------

def cmd_metric(args: argparse.Namespace) -> dict[str, Any]:
    """Ghi một dòng KPI cho một đợt xử lý của agent vào bảng agent_metrics.

    Args:
        args: Tham số CLI gồm agent, items, dod_pass, dod_total, tokens, fp, wave, note.

    Returns:
        Từ điển trạng thái kèm id bản ghi và tỷ lệ DoD của đợt.
    """
    conn = get_db_connection(args.db)
    try:
        ts = now_iso()
        cur = conn.execute(
            """
            INSERT INTO agent_metrics
                (agent_id, run_ts, items, dod_pass, dod_total, tokens, fp_flags, wave, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (args.agent, ts, args.items, args.dod_pass, args.dod_total,
             args.tokens, args.fp, args.wave, args.note, ts),
        )
        conn.commit()
        rate = (args.dod_pass / args.dod_total) if args.dod_total else None
        return {
            "status": "success",
            "metric_id": cur.lastrowid,
            "agent_id": args.agent,
            "dod_pass_rate": round(rate, 4) if rate is not None else None,
            "timestamp": ts,
        }
    finally:
        conn.close()


def query_agent_metrics(db_path: str = DEFAULT_DB_PATH, agent: str | None = None) -> dict[str, Any]:
    """Tổng hợp KPI tích lũy theo từng agent từ bảng agent_metrics.

    Args:
        db_path: Đường dẫn harness.db.
        agent: Lọc theo một agent_id cụ thể, mặc định gộp toàn bộ.

    Returns:
        Từ điển gồm danh sách rollup KPI theo agent.
    """
    conn = get_db_connection(db_path)
    try:
        sql = (
            "SELECT agent_id, COUNT(*) AS runs, SUM(items) AS items, "
            "SUM(dod_pass) AS dod_pass, SUM(dod_total) AS dod_total, "
            "SUM(tokens) AS tokens, SUM(fp_flags) AS fp_flags, MAX(run_ts) AS last_run "
            "FROM agent_metrics"
        )
        params: tuple = ()
        if agent:
            sql += " WHERE agent_id = ?"
            params = (agent,)
        sql += " GROUP BY agent_id ORDER BY agent_id"

        rollup = []
        for r in conn.execute(sql, params).fetchall():
            total = r["dod_total"] or 0
            rollup.append({
                "agent_id": r["agent_id"],
                "runs": r["runs"],
                "items": r["items"],
                "dod_pass": r["dod_pass"],
                "dod_total": total,
                "dod_pass_rate": round(r["dod_pass"] / total, 4) if total else None,
                "tokens": r["tokens"],
                "fp_flags": r["fp_flags"],
                "last_run": r["last_run"],
            })
        return {"status": "success", "agents": rollup, "timestamp": now_iso()}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Git Codebase Governance & Lifecycle (US-030)
# ---------------------------------------------------------------------------

def cmd_git_status(args: argparse.Namespace) -> dict[str, Any]:
    """Kiểm tra trạng thái Git repository, branch, head commit và các tệp cấm."""
    branch = get_git_branch()
    commit = get_git_head_commit()
    dirty = is_git_working_tree_dirty()

    forbidden: list[str] = []
    res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    status_lines = [l.strip() for l in res.stdout.splitlines() if l.strip()]
    for line in status_lines:
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            status_code, fname = parts[0], parts[1]
            if "D" in status_code:
                continue
            if "-DESKTOP-" in fname or "-FPA-" in fname:
                forbidden.append(f"OneDrive conflict file: {fname}")
            elif fname.endswith((".db-wal", ".db-shm")) or (fname.endswith(".db") and not fname.startswith("data/archive")):
                forbidden.append(f"Database runtime file: {fname}")
            elif fname.endswith(".xlsx") and not fname.startswith("docs/"):
                forbidden.append(f"Binary spreadsheet: {fname}")

    return {
        "status": "success",
        "branch": branch,
        "commit": commit,
        "is_dirty": dirty,
        "status_lines": status_lines[:25],
        "forbidden_files": forbidden,
        "clean_for_closure": not dirty and len(forbidden) == 0,
    }


def cmd_git_checkpoint(args: argparse.Namespace) -> dict[str, Any]:
    """Tạo commit checkpoint đóng phiên hoặc lưu vết tác vụ Tiny/Hygiene."""
    branch = get_git_branch()
    if not is_git_working_tree_dirty():
        return {
            "status": "success",
            "message": "Working tree already clean, nothing to commit",
            "commit": get_git_head_commit(),
            "branch": branch,
        }

    subprocess.run(["git", "add", "-u"], capture_output=True, text=True)
    msg = args.summary
    if not msg.startswith(("feat", "fix", "docs", "chore", "refactor", "test")):
        msg = f"chore(checkpoint): {msg}"

    res = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True)
    if res.returncode != 0:
        return {"status": "error", "message": f"Git commit failed: {res.stderr.strip()}"}

    commit = get_git_head_commit()
    pushed = False
    if getattr(args, "push", False) and branch:
        res_push = subprocess.run(["git", "push", "origin", branch], capture_output=True, text=True)
        pushed = (res_push.returncode == 0)

    return {
        "status": "success",
        "action": "checkpoint_created",
        "commit": commit,
        "branch": branch,
        "pushed": pushed,
        "message": msg,
    }


def cmd_git_verify(args: argparse.Namespace) -> dict[str, Any]:
    """Chạy cổng kiểm soát chất lượng pre-commit: cú pháp AST và kiểm tra tệp cấm."""
    import ast
    ast_errors: list[str] = []
    py_files_checked = 0
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in [".venv", "__pycache__", ".git", ".pytest_cache", ".kilo", "scratch"]]
        for f in files:
            if f.endswith(".py"):
                fpath = os.path.join(root, f)
                py_files_checked += 1
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as pf:
                        ast.parse(pf.read(), filename=fpath)
                except SyntaxError as se:
                    ast_errors.append(f"{fpath}:{se.lineno}: {se.msg}")

    status_info = cmd_git_status(args)
    passed = len(ast_errors) == 0 and len(status_info["forbidden_files"]) == 0
    return {
        "status": "success" if passed else "error",
        "ast_checked_files": py_files_checked,
        "ast_errors": ast_errors,
        "forbidden_files": status_info["forbidden_files"],
        "is_clean": passed,
    }


def cmd_git_template(args: argparse.Namespace) -> dict[str, Any]:
    """Sinh chuỗi thông điệp commit chuẩn ngành theo Conventional Commits 1.0.0."""
    c_type = args.type.lower().strip()
    scope = f"({args.scope.lower().strip()})" if getattr(args, "scope", None) else ""
    story_suffix = f" ({args.story.upper().strip()})" if getattr(args, "story", None) else ""
    title = args.title.strip()
    if title and len(title) > 1:
        title = title[0].lower() + title[1:]
    elif title:
        title = title.lower()
    if title.endswith("."):
        title = title[:-1].strip()

    header = f"{c_type}{scope}: {title}{story_suffix}"
    body = getattr(args, "body", None)
    lines = [header]
    if body:
        lines.append("")
        lines.append(body.strip())

    full_message = "\n".join(lines)
    return {
        "status": "success",
        "header": header,
        "message": full_message,
        "length": len(header),
        "compliant_length": len(header) <= 72,
    }


# ---------------------------------------------------------------------------
# CLI Argument Parser Setup
# ---------------------------------------------------------------------------

def cmd_doc(args: argparse.Namespace) -> dict[str, Any]:
    """Run a knowledge-document action under the ADR-0021 contract.

    Args:
        args: Parsed arguments with `doc_action` and action-specific options.

    Returns:
        Result mapping; status is "error" when lint finds violations.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import knowledge

    root = knowledge.REPO_ROOT
    if args.doc_action == "new":
        return {"status": "success", **knowledge.new_doc(
            root, args.type, args.title, lane=args.lane, author=args.author, slug=args.slug,
            wave=args.wave, db_path=args.db, adopt_id=args.id)}
    if args.doc_action == "lint":
        only = knowledge.staged_paths(root) if args.staged else None
        findings = knowledge.lint(root, only)
        return {"status": "error" if findings else "success", "count": len(findings),
                "findings": [str(f) for f in findings]}
    if args.doc_action == "index":
        return knowledge.write_index(root)
    if args.doc_action == "sync":
        return knowledge.sync_db(root, args.db)
    return {"status": "error", "message": f"unknown doc action {args.doc_action}"}


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

    am_p = query_sub.add_parser("agent-metrics", help="Query per-agent KPI rollup (Spine 3)")
    am_p.add_argument("--agent", help="Filter by a specific agent_id from registry.yaml")
    
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
    s_comp.add_argument("--commit", action="store_true", help="Automatically commit modified files with Conventional Commit msg (US-XXX)")
    
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
    
    # metric (Spine 3 — per-agent KPI ledger)
    met_p = subparsers.add_parser("metric", help="Record a per-agent KPI row for one processing wave")
    met_p.add_argument("--agent", required=True, help="agent_id matching registry.yaml")
    met_p.add_argument("--items", type=int, default=0, help="Số bài xử lý trong đợt")
    met_p.add_argument("--dod-pass", type=int, default=0, dest="dod_pass", help="Số bài đạt DoD")
    met_p.add_argument("--dod-total", type=int, default=0, dest="dod_total", help="Số bài chấm DoD")
    met_p.add_argument("--tokens", type=int, help="Token tiêu thụ đợt (bỏ trống cho operator)")
    met_p.add_argument("--fp", type=int, default=0, help="Số cờ nghi ngờ false-positive")
    met_p.add_argument("--wave", help="Nhãn đợt/batch")
    met_p.add_argument("--note", help="Ghi chú RCA ngắn")

    # git
    git_p = subparsers.add_parser("git", help="Git codebase governance & lifecycle tools")
    git_sub = git_p.add_subparsers(dest="git_action", required=True)
    git_sub.add_parser("status", help="Inspect git branch, head commit, dirty tree and forbidden files")
    git_chk = git_sub.add_parser("checkpoint", help="Create a clean session closure commit")
    git_chk.add_argument("--summary", required=True, help="Checkpoint summary message")
    git_chk.add_argument("--push", action="store_true", help="Push to remote after checkpoint commit")
    git_sub.add_parser("verify", help="Run pre-commit quality gate (AST, forbidden files, hygiene)")
    git_tmpl = git_sub.add_parser("template", help="Generate a compliant Conventional Commit message")
    git_tmpl.add_argument("--type", required=True, choices=["feat", "fix", "refactor", "perf", "docs", "test", "chore"], help="Commit type")
    git_tmpl.add_argument("--scope", help="Commit scope (e.g. core, harness, article-lane)")
    git_tmpl.add_argument("--story", help="Story ID (e.g. US-030)")
    git_tmpl.add_argument("--title", required=True, help="Short commit description in imperative mood")
    git_tmpl.add_argument("--body", help="Optional commit body explaining reason/context")

    # knowledge documents (ADR-0021)
    doc_p = subparsers.add_parser("doc", help="Create, lint, index and sync knowledge documents")
    doc_sub = doc_p.add_subparsers(dest="doc_action", required=True)
    d_new = doc_sub.add_parser("new", help="Allocate an id and create a document from its template")
    d_new.add_argument("--type", required=True,
                       choices=["adr", "story", "proposal", "plan", "fact", "rule", "run", "runbook"])
    d_new.add_argument("--title", required=True, help="Title in English")
    d_new.add_argument("--lane", default="normal", choices=["tiny", "normal", "high-risk"])
    d_new.add_argument("--author", default="agent", help="Agent or human recorded in authors")
    d_new.add_argument("--slug", help="File slug; derived from the title when omitted")
    d_new.add_argument("--wave", help="Wave code, required for --type run")
    d_new.add_argument("--id", help="Adopt an adr or story id already registered in harness.db")
    d_lint = doc_sub.add_parser("lint", help="Validate governed documents against docs/knowledge/schema.yaml")
    d_lint.add_argument("--staged", action="store_true", help="Report only on staged files")
    doc_sub.add_parser("index", help="Regenerate docs/INDEX.md from frontmatter")
    doc_sub.add_parser("sync", help="Upsert story and decision rows in harness.db from frontmatter")

    # audit & propose
    audit_p = subparsers.add_parser("audit", help="Run harness drift & entropy audit")
    audit_p.add_argument("--codebase", action="store_true", help="Include Git codebase and AST hygiene audit")
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


def _force_utf8_stdio() -> None:
    """Cấu hình lại luồng xuất chuẩn sang UTF-8 chống lỗi charmap trên console Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main() -> None:
    _force_utf8_stdio()
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
            elif args.query_target == "agent-metrics":
                res = query_agent_metrics(args.db, getattr(args, "agent", None))
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
        elif args.command == "metric":
            res = cmd_metric(args)
        elif args.command == "git":
            if args.git_action == "status":
                res = cmd_git_status(args)
            elif args.git_action == "checkpoint":
                res = cmd_git_checkpoint(args)
            elif args.git_action == "verify":
                res = cmd_git_verify(args)
            elif args.git_action == "template":
                res = cmd_git_template(args)
        elif args.command == "doc":
            res = cmd_doc(args)
        elif args.command == "audit":
            res = cmd_audit(args.db, check_codebase=getattr(args, "codebase", False))
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
