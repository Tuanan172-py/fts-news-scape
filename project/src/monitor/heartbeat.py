"""
Heartbeat + metrics — biết ngay khi scraper chết (spec §4.3).

Ghi vào SQLite cùng DB (bảng nhỏ, WAL + busy_timeout đủ an toàn —
không cần qua DBWriter queue vốn dành cho khối lượng articles).
"""

from __future__ import annotations

from loguru import logger

from src.core.models import ScrapeResult, now_vn_iso
from src.db.store import ArticleStore


class Heartbeat:
    def __init__(self, store: ArticleStore):
        self.store = store

    def record_start(self, scraper_name: str) -> None:
        conn = self.store._connect()
        try:
            conn.execute(
                "INSERT INTO scraper_heartbeat (scraper_name, last_run_ts, status) "
                "VALUES (?, ?, 'running') "
                "ON CONFLICT(scraper_name) DO UPDATE SET "
                "last_run_ts=excluded.last_run_ts, status='running'",
                (scraper_name, now_vn_iso()))
            conn.commit()
        finally:
            conn.close()

    def record_result(self, result: ScrapeResult) -> None:
        failed = result.fetched == 0 and bool(result.errors)
        status = "failed" if failed else "ok"
        error_msg = "; ".join(result.errors[:3]) if result.errors else ""
        conn = self.store._connect()
        try:
            conn.execute(
                "INSERT INTO scraper_heartbeat "
                "(scraper_name, last_run_ts, status, error_msg, consecutive_failures, cycle_count) "
                "VALUES (?, ?, ?, ?, ?, 1) "
                "ON CONFLICT(scraper_name) DO UPDATE SET "
                "last_run_ts=excluded.last_run_ts, status=excluded.status, "
                "error_msg=excluded.error_msg, "
                "consecutive_failures=CASE WHEN excluded.status='failed' "
                "  THEN scraper_heartbeat.consecutive_failures + 1 ELSE 0 END, "
                "cycle_count=scraper_heartbeat.cycle_count + 1",
                (result.scraper, now_vn_iso(), status, error_msg,
                 1 if failed else 0))
            conn.execute(
                "INSERT INTO scraper_metrics "
                "(ts, scraper_name, articles_fetched, articles_new, errors, duration_ms) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (now_vn_iso(), result.scraper, result.fetched, len(result.new),
                 len(result.errors), int(result.duration_s * 1000)))
            conn.commit()
        finally:
            conn.close()
        if failed:
            logger.error("[heartbeat] {} FAILED: {}", result.scraper, error_msg)
