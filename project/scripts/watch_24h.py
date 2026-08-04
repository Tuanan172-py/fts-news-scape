"""
24h stability watcher — snapshot mỗi giờ: article counts, heartbeat states,
cycle durations → CSV. Chạy song song với orchestrator.

Usage: python scripts/watch_24h.py [--hours 24] [--out data/watch_24h.csv]
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import load_settings
from src.core.models import now_vn_iso
from src.db.store import ArticleStore
from src.monitor.health import check


def snapshot(store: ArticleStore) -> list[dict]:
    from datetime import datetime, timedelta
    from src.core.models import VN_TZ

    report, _ = check(store)
    cutoff = (datetime.now(VN_TZ) - timedelta(hours=1)).isoformat(timespec="seconds")
    conn = store._connect()
    avg = {r["scraper_name"]: r["avg_ms"] for r in conn.execute(
        "SELECT scraper_name, AVG(duration_ms) AS avg_ms FROM scraper_metrics "
        "WHERE ts >= ? GROUP BY scraper_name", (cutoff,))}
    conn.close()
    ts = now_vn_iso()
    return [{**r, "ts": ts, "avg_cycle_ms_1h": round(avg.get(r["scraper"], 0) or 0)}
            for r in report]


def main(hours: float, out: str) -> int:
    store = ArticleStore(load_settings()["database"]["path"])
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["ts", "scraper", "state", "status", "last_run", "consec_fails",
              "cycles", "articles_24h", "avg_cycle_ms_1h", "error"]
    new_file = not out_path.exists()
    end = time.time() + hours * 3600
    while time.time() < end:
        rows = snapshot(store)
        with out_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            if new_file:
                w.writeheader()
                new_file = False
            w.writerows(rows)
        print(f"{now_vn_iso()} snapshot: "
              + " | ".join(f"{r['scraper']}={r['state']}" for r in rows))
        time.sleep(3600)
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=float, default=24)
    p.add_argument("--out", default="data/watch_24h.csv")
    a = p.parse_args()
    sys.exit(main(a.hours, a.out))
