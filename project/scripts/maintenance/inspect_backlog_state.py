"""Inspect the operational warehouse and wave runner status across databases."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.stdio import force_utf8_stdio
from src.ops.config import resolve_paths

force_utf8_stdio()


def main() -> None:
    """Run read-only inspection of monocle.db, ops.db, and harness.db."""
    paths = resolve_paths()
    from src.db.preflight import resolve_db_path

    monocle_db = resolve_db_path()
    ops_db = paths.ops_db
    harness_db = PROJECT_ROOT.parent / "harness.db"

    print("================================================================================")
    print(" 🔍 WAREHOUSE BACKLOG STATE & WAVE RUNNER FORENSIC INSPECTION")
    print("================================================================================")

    # 1. Monocle.db checks
    print(f"\n[1] MONOCLE.DB ({monocle_db})")
    conn_m = sqlite3.connect(f"file:{monocle_db}?mode=ro", uri=True)
    try:
        cur = conn_m.cursor()
        total_articles = cur.execute("SELECT count(*) FROM articles").fetchone()[0]
        dod_pass_articles = cur.execute(
            "SELECT count(DISTINCT article_id) FROM agent_outputs WHERE dod_pass = 1"
        ).fetchone()[0]
        agent_outputs_total = cur.execute("SELECT count(*) FROM agent_outputs").fetchone()[0]
        pending_total = total_articles - dod_pass_articles

        print(f"  Total articles in warehouse            : {total_articles:,}")
        print(f"  Distinct articles with dod_pass = 1    : {dod_pass_articles:,}")
        print(f"  Total agent_outputs records            : {agent_outputs_total:,}")
        print(f"  Backlog remaining (pending total)      : {pending_total:,} ({(pending_total/total_articles*100):.2f}%)")

        # Tier breakdown of pending articles
        from scripts.article_pack import watchlist_universe, tier_of
        from src.agent.entities import load_registry

        reg = load_registry()
        watched, industries = watchlist_universe(reg)

        rows_pending = cur.execute("""
            SELECT a.url_title_hash, a.title FROM articles a
            WHERE NOT EXISTS (
                SELECT 1 FROM agent_outputs g 
                WHERE g.article_id = a.url_title_hash AND g.dod_pass = 1
            )
        """).fetchall()

        tier1_count = 0
        tier2_count = 0
        reasons: dict[str, int] = {}
        for row in rows_pending:
            t, reason = tier_of(row[1], reg, watched, industries)
            if t == 1:
                tier1_count += 1
                base_reason = reason.split(":")[0] if ":" in reason else reason
                reasons[base_reason] = reasons.get(base_reason, 0) + 1
            else:
                tier2_count += 1

        print(f"\n  Backlog Breakdown by Priority Tier:")
        print(f"    • Tier 1 (Watchlist & Macro urgent)  : {tier1_count:,} ({(tier1_count/pending_total*100):.2f}%)")
        for rk, rc in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"        - {rk:<18}: {rc:,}")
        print(f"    • Tier 2/3 (General market news)     : {tier2_count:,} ({(tier2_count/pending_total*100):.2f}%)")
    finally:
        conn_m.close()

    # 2. Ops.db checks
    print(f"\n[2] OPS.DB ({ops_db})")
    conn_ops = sqlite3.connect(f"file:{ops_db}?mode=ro", uri=True)
    try:
        cur_ops = conn_ops.cursor()
        cols = [col[1] for col in cur_ops.execute("PRAGMA table_info(ops_waves)").fetchall()]
        select_cols = [c for c in ["wave_id", "status", "step", "n_articles", "opened_at", "updated_at", "error"] if c in cols]
        waves = cur_ops.execute(
            f"SELECT {', '.join(select_cols)} FROM ops_waves ORDER BY rowid DESC LIMIT 10"
        ).fetchall()
        print(f"  ops_waves columns: {cols}")
        print("  Recent Waves in ops_waves:")
        for w in waves:
            row_str = " | ".join(f"{k}: {v}" for k, v in zip(select_cols, w))
            print(f"    • {row_str}")

        # Check wave W_BKL_01_10301528 specifically
        w_bkl = cur_ops.execute(
            f"SELECT {', '.join(select_cols)} FROM ops_waves WHERE wave_id LIKE '%10301528%'"
        ).fetchall()
        print(f"\n  Specific status of W_BKL_01_10301528:")
        if w_bkl:
            for wb in w_bkl:
                row_str = " | ".join(f"{k}: {v}" for k, v in zip(select_cols, wb))
                print(f"    • {row_str}")
        else:
            print("    • No entry in ops_waves (was run via run_backlog_waves / article_run directly outside ops_daemon)")

        # Reserved articles check
        from src.ops.store import RELEASED_WAVE_STATUSES
        marks = ",".join("?" * len(RELEASED_WAVE_STATUSES))
        unreleased = cur_ops.execute(
            f"SELECT COUNT(DISTINCT a.article_id) FROM ops_wave_articles a "
            f"JOIN ops_waves w ON w.wave_id = a.wave_id WHERE w.status NOT IN ({marks})",
            RELEASED_WAVE_STATUSES,
        ).fetchone()[0]
        print(f"\n  Unreleased reserved articles in ops.db: {unreleased}")

    finally:
        conn_ops.close()

    # 3. Harness.db token_ledger check
    print(f"\n[3] HARNESS.DB ({harness_db})")
    if harness_db.exists():
        conn_h = sqlite3.connect(f"file:{harness_db}?mode=ro", uri=True)
        try:
            cur_h = conn_h.cursor()
            ledger_rows = cur_h.execute(
                "SELECT wave, ts, n_items, miss_tokens, hit_tokens, out_tokens, quota_tokens, billed_usd "
                "FROM token_ledger WHERE wave LIKE '%BKL%' ORDER BY id DESC"
            ).fetchall()
            print("  Token Ledger records for Backlog waves:")
            for lr in ledger_rows:
                print(f"    • Wave: {lr[0]} | ts: {lr[1]} | items: {lr[2]} | miss: {lr[3]:,} | hit: {lr[4]:,} | out: {lr[5]:,} | quota: {lr[6]:,} | USD: ${lr[7]:.4f}")
        finally:
            conn_h.close()

    print("\n================================================================================")


if __name__ == "__main__":
    main()
