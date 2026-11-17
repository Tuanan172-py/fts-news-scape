"""Reconcile the store against sitemaps, backfill missing URLs and recover lost Bronze files (rule 10, ADR 0013)."""

from __future__ import annotations

import argparse
import json
import math
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
from src.pipeline.reconcile import (REFERENCE_DOMAINS, REFERENCE_EVERY_MINUTES, REFERENCE_TIMEOUT,
                                    reconcile)

force_utf8_stdio()

RED_MISSING_PCT = 2.0     # rule 10 §3: more than 2% missing in a day is RED
MIN_DAYS = 3              # reconcile window when the previous run is recent
MAX_DAYS = 35             # cap for the window after a long outage
LAST_KEY = "reconcile_last_ts:{domain}"
FAIL_KEY = "reconcile_fail:{domain}"


def coverage_rows(store: ArticleStore, days: int | None = None) -> list[dict]:
    """Read recent capture coverage from the `capture_coverage` table.

    Args:
        store: ArticleStore of the operational DB.
        days: Number of most recent days to read. Defaults to 2.

    Returns:
        Rows with day, source, ref_n, in_db_n, missing_n, pct_missing and the red flag.
    """
    days = 2 if days is None else days
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
    print("Nguồn không có kênh đối chiếu độc lập: fireant.vn (API đọc lùi tới mốc lần chạy đủ trước)")
    return 1 if any(r["red"] for r in rows) else 0


def adaptive_days(last_ts: float | None, now: float, floor: int = MIN_DAYS) -> int:
    """Size the reconcile window so it reaches back past the last successful run.

    A machine off from Friday evening to Monday morning gets a five-day window, so Friday's
    evening articles are checked again.

    Args:
        last_ts: Epoch seconds of the domain's last successful reconcile, or None.
        now: Current epoch seconds.
        floor: Smallest window in days.

    Returns:
        Days to reconcile, including today, between `floor` and MAX_DAYS.
    """
    if last_ts is None:
        return floor
    gap_days = max(0.0, now - last_ts) / 86400
    return max(floor, min(MAX_DAYS, math.ceil(gap_days) + 2))


def _float_state(store: ArticleStore, key: str) -> float | None:
    """Read an epoch-seconds value from `pipeline_state`."""
    raw = store.get_state(key)
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def _timeout_for(url: str) -> int:
    """Return the request timeout for a reference URL."""
    for domain, seconds in REFERENCE_TIMEOUT.items():
        if domain in url:
            return seconds
    return 30


def reconcile_due(store: ArticleStore, domains: tuple[str, ...], *, min_interval: float,
                  fixed_days: int | None, force: bool, now: float) -> dict[str, int]:
    """Pick the domains to reconcile now and the window of each.

    Args:
        store: ArticleStore of the operational DB.
        domains: Candidate domains.
        min_interval: Caller's minimum interval in minutes.
        fixed_days: Window forced by the operator, or None for the adaptive window.
        force: Ignore the intervals.
        now: Current epoch seconds.

    Returns:
        Mapping of domain to days, in the order given.
    """
    legacy = _float_state(store, "reconcile_last_ts")
    due: dict[str, int] = {}
    for domain in domains:
        last = _float_state(store, LAST_KEY.format(domain=domain))
        every = max(min_interval, REFERENCE_EVERY_MINUTES.get(domain, 0))
        if not force and last is not None and (now - last) < every * 60:
            continue
        due[domain] = fixed_days or adaptive_days(last if last is not None else legacy, now)
    return due


def main(argv: list[str] | None = None) -> int:
    """Run one subcommand: reconcile, backfill, recapture, run, status or rekey.

    Args:
        argv: Command-line arguments; defaults to `sys.argv`.

    Returns:
        Exit code; `status` returns 1 when any day exceeds the missing threshold.
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["reconcile", "backfill", "recapture", "run", "status", "rekey"])
    ap.add_argument("--days", type=int, default=None,
                    help="cửa sổ đối chiếu cố định; mặc định tự giãn theo lần đối chiếu thành công trước")
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
        if args.cmd in ("reconcile", "run"):
            now = time.time()
            due = reconcile_due(store, domains, min_interval=args.min_interval_minutes,
                                fixed_days=args.days, force=args.cmd == "reconcile", now=now)
            if not due:
                print("[reconcile] bỏ qua: lần đối chiếu trước của mọi nguồn còn mới")
            for dom, days in due.items():
                conn = store._connect()
                try:
                    rep = reconcile(conn, lambda u: http.get(u, timeout=_timeout_for(u)),
                                    domains=(dom,), days=days)
                except Exception as exc:  # noqa: BLE001 - one broken source must not stop the others
                    rep = {dom: {}}
                    print(f"[reconcile] {dom}: lỗi {type(exc).__name__}: {exc}")
                finally:
                    conn.close()
                per_day = rep.get(dom) or {}
                if not per_day:
                    store.set_state(FAIL_KEY.format(domain=dom), json.dumps(
                        {"at": now, "days": days, "reason": "kênh đối chiếu không trả bài nào"},
                        ensure_ascii=False))
                    print(f"[reconcile] {dom}: kênh đối chiếu không trả bài nào ({days} ngày)")
                    continue
                store.set_state(LAST_KEY.format(domain=dom), str(now))
                store.set_state("reconcile_last_ts", str(now))
                miss = sum(v["missing_n"] for v in per_day.values())
                ref = sum(v["ref_n"] for v in per_day.values())
                print(f"[reconcile] {dom}: {days} ngày, tham chiếu {ref}, thiếu {miss}")
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
