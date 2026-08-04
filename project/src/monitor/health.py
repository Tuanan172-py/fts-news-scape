"""
Health check CLI — `python -m src.monitor.health`.

Exit 0 = tất cả OK; exit 1 = có scraper STALE (>30 phút) hoặc
CRITICAL (≥3 lần fail liên tiếp) hoặc FAILED.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta

from src.core.config import load_settings
from src.core.models import VN_TZ
from src.db.store import ArticleStore

STALE_MINUTES = 30
CRITICAL_CONSECUTIVE = 3


def check(store: ArticleStore) -> tuple[list[dict], bool]:
    now = datetime.now(VN_TZ)
    # ts lưu ISO +07:00 → tính cutoff cùng format trong Python, tránh lệch
    # múi giờ của datetime('now') phía SQLite
    cutoff_24h = (now - timedelta(days=1)).isoformat(timespec="seconds")
    conn = store._connect()
    try:
        rows = conn.execute(
            "SELECT h.*, COALESCE(m.n24, 0) AS articles_24h FROM scraper_heartbeat h "
            "LEFT JOIN (SELECT scraper_name, SUM(articles_new) AS n24 "
            "           FROM scraper_metrics WHERE ts >= ? "
            "           GROUP BY scraper_name) m "
            "ON m.scraper_name = h.scraper_name", (cutoff_24h,)).fetchall()
    finally:
        conn.close()
    report, all_ok = [], True
    for r in rows:
        state = "OK"
        last_run = r["last_run_ts"] or ""
        try:
            age = now - datetime.fromisoformat(last_run)
        except ValueError:
            age = None
        if r["consecutive_failures"] >= CRITICAL_CONSECUTIVE:
            state = "CRITICAL"
        elif r["status"] == "failed":
            state = "FAILED"
        elif age is not None and age > timedelta(minutes=STALE_MINUTES):
            state = "STALE"
        if state != "OK":
            all_ok = False
        report.append({
            "scraper": r["scraper_name"], "state": state,
            "last_run": last_run, "status": r["status"],
            "consec_fails": r["consecutive_failures"],
            "cycles": r["cycle_count"], "articles_24h": r["articles_24h"],
            "error": (r["error_msg"] or "")[:60],
        })
    return report, all_ok


def main() -> int:
    settings = load_settings()
    store = ArticleStore(settings["database"]["path"])
    report, all_ok = check(store)
    if not report:
        print("No heartbeat data — chưa có scraper nào chạy.")
        return 1
    fmt = "{:<12} {:<9} {:<26} {:>6} {:>7} {:>12}  {}"
    print(fmt.format("SCRAPER", "STATE", "LAST RUN", "FAILS", "CYCLES",
                     "ARTICLES/24H", "ERROR"))
    for r in report:
        print(fmt.format(r["scraper"], r["state"], r["last_run"],
                         r["consec_fails"], r["cycles"], r["articles_24h"],
                         r["error"]))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
