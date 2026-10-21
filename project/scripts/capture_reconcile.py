"""Reconcile the store against sitemaps, backfill missing URLs and recover lost Bronze files (rule 10, ADR 0013)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import load_settings
from src.core.stdio import force_utf8_stdio
from src.crawler.http_client import HTTPClient
from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.pipeline.backfill import backfill_pending, make_scraper_factory, recapture_lost_bronze
from src.pipeline.reconcile import REFERENCE_DOMAINS, reconcile

force_utf8_stdio()

RED_MISSING_PCT = 2.0     # rule 10 §3: more than 2% missing in a day is RED


def coverage_rows(store: ArticleStore, days: int) -> list[dict]:
    """Read recent capture coverage from the `capture_coverage` table.

    Args:
        store: ArticleStore of the operational DB.
        days: Number of most recent days to read.

    Returns:
        Rows with day, source, ref_n, in_db_n, missing_n, pct_missing and the red flag.
    """
    conn = store._connect_ro()
    try:
        rows = conn.execute(
            "SELECT day, source_domain, ref_n, in_db_n, missing_n, backfilled_n, checked_at "
            "FROM capture_coverage WHERE day >= date('now', ?, 'localtime') "
            "ORDER BY day DESC, source_domain", (f"-{days - 1} days",)).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        pct = 100.0 * r["missing_n"] / r["ref_n"] if r["ref_n"] else 0.0
        out.append({**dict(r), "pct_missing": round(pct, 1), "red": pct > RED_MISSING_PCT})
    return out


def cmd_status(store: ArticleStore, days: int) -> int:
    """Print the capture coverage table and the backfill queue.

    Args:
        store: ArticleStore of the operational DB.
        days: Number of most recent days to print.

    Returns:
        1 if any day exceeds the missing threshold, otherwise 0.
    """
    rows = coverage_rows(store, days)
    print(f"{'ngày':10} {'nguồn':26} {'sitemap':>8} {'có':>6} {'thiếu':>6} {'%thiếu':>7}")
    for r in rows:
        flag = "ĐỎ" if r["red"] else "ok"
        print(f"{r['day']:10} {r['source_domain']:26} {r['ref_n']:>8} {r['in_db_n']:>6} "
              f"{r['missing_n']:>6} {r['pct_missing']:>6}% {flag}")
    conn = store._connect_ro()
    try:
        pend = conn.execute("SELECT source_domain, COUNT(*) FROM discovered_urls "
                            "WHERE state='discovered' GROUP BY 1").fetchall()
        dead = conn.execute("SELECT COUNT(*) FROM discovered_urls WHERE state='dead_letter'").fetchone()[0]
    finally:
        conn.close()
    print("\nChờ cào bù:", {r[0]: r[1] for r in pend} or "không có", "| dead_letter:", dead)
    no_ref = "vietstock.vn, vietnambiz.vn, thoibaotaichinhvietnam.vn"
    print(f"Nguồn chưa có kênh đối chiếu độc lập: {no_ref}")
    return 1 if any(r["red"] for r in rows) else 0


def _reconciled_recently(store: ArticleStore, minutes: float) -> bool:
    """Check whether the last reconciliation is still within the minimum interval.

    Args:
        store: ArticleStore of the operational DB.
        minutes: Minimum interval in minutes; 0 means always reconcile.

    Returns:
        True if the previous run happened less than `minutes` minutes ago.
    """
    if minutes <= 0:
        return False
    last = store.get_state("reconcile_last_ts")
    try:
        return last is not None and (time.time() - float(last)) < minutes * 60
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    """Run one subcommand: reconcile, backfill, recapture, run, status or rekey.

    Args:
        argv: Command-line arguments; defaults to `sys.argv`.

    Returns:
        Exit code; `status` returns 1 when any day exceeds the missing threshold.
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["reconcile", "backfill", "recapture", "run", "status", "rekey"])
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--budget", type=float, default=600.0, help="giây tối đa mỗi lượt")
    ap.add_argument("--domain", default=None)
    ap.add_argument("--db", default=None)
    ap.add_argument("--min-interval-minutes", type=float, default=0.0,
                    help="lệnh run bỏ qua pha đối chiếu nếu lần trước còn mới hơn mốc này")
    args = ap.parse_args(argv)

    settings = load_settings()
    store = ArticleStore(args.db or settings["database"]["path"])
    if args.cmd == "status":
        return cmd_status(store, args.days)
    if args.cmd == "rekey":
        from src.db import registry

        conn = store._connect()
        try:
            stats = registry.rekey(conn)
            conn.commit()
        finally:
            conn.close()
        print(f"[rekey] {stats}")
        return 0

    http = HTTPClient(rate_limit_delay=settings["http"]["rate_limit"],
                      max_retries=settings["http"]["max_retries"])
    domains = (args.domain,) if args.domain else REFERENCE_DOMAINS
    dedup = DedupCache(store, legacy_json_path="")
    try:
        if args.cmd == "run" and _reconciled_recently(store, args.min_interval_minutes):
            print("[reconcile] bỏ qua: lần đối chiếu trước còn mới")
        elif args.cmd in ("reconcile", "run"):
            conn = store._connect()
            try:
                rep = reconcile(conn, lambda u: http.get(u, timeout=30), domains=domains,
                                days=args.days)
            finally:
                conn.close()
            store.set_state("reconcile_last_ts", str(time.time()))
            for dom, per_day in rep.items():
                miss = sum(v["missing_n"] for v in per_day.values())
                ref = sum(v["ref_n"] for v in per_day.values())
                print(f"[reconcile] {dom}: sitemap {ref}, thiếu {miss}")
        factory = make_scraper_factory(http, dedup)
        if args.cmd in ("backfill", "run"):
            s = backfill_pending(store, factory, limit=args.limit, domain=args.domain,
                                 budget_seconds=args.budget)
            print(f"[backfill] {s}")
        if args.cmd == "recapture":
            s = recapture_lost_bronze(store, factory, limit=args.limit, budget_seconds=args.budget)
            print(f"[recapture] {s}")
    finally:
        dedup.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
