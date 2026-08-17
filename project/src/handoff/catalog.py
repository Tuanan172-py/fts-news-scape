"""
Catalog — bảng `work_items` điều phối handoff producer↔consumer (phase-03).

Producer append work_items; consumer (agent bất kỳ) claim → done/failed. Exactly-once:
- idempotency key = UNIQUE(article_id, raw_sha256) → enqueue INSERT OR IGNORE.
- claim atomic (BEGIN IMMEDIATE + UPDATE ... WHERE status='pending') → không double-claim.
Held: change_state ∈ {SELECTOR_BROKEN, TEMPLATE_DRIFT} → status='held' (không giao agent).
DDL nằm ở store._SCHEMA (tập trung). Class này chỉ thao tác.
"""

from __future__ import annotations

from loguru import logger

from src.core.models import now_vn_iso

_HELD_STATES = {"SELECTOR_BROKEN", "TEMPLATE_DRIFT"}


class Catalog:
    def __init__(self, store):
        self.store = store  # ArticleStore

    def enqueue(self, article_id: str, raw_sha256: str, domain: str,
                package_path: str, change_state: str, *, force_held: bool = False) -> str:
        """INSERT OR IGNORE (idempotent). Trả status thực tế của item.
        force_held=True (vd package fail schema) → luôn held, không giao agent."""
        status = "held" if (force_held or change_state in _HELD_STATES) else "pending"
        conn = self.store.connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO work_items "
                "(article_id, raw_sha256, domain, package_path, status, change_state, enqueued_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (article_id, raw_sha256, domain, package_path, status, change_state, now_vn_iso()))
            conn.commit()
            row = conn.execute(
                "SELECT status FROM work_items WHERE article_id=? AND raw_sha256=?",
                (article_id, raw_sha256)).fetchone()
            return row["status"] if row else status
        finally:
            conn.close()

    def list_pending(self, limit: int = 50) -> list[dict]:
        conn = self.store.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM work_items WHERE status='pending' "
                "ORDER BY enqueued_at LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def claim(self, worker_id: str) -> dict | None:
        """Claim 1 item pending → claimed (atomic). None nếu hết việc."""
        conn = self.store.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM work_items WHERE status='pending' "
                "ORDER BY enqueued_at LIMIT 1").fetchone()
            if row is None:
                conn.commit()
                return None
            conn.execute(
                "UPDATE work_items SET status='claimed', claimed_by=?, claimed_at=? "
                "WHERE id=? AND status='pending'",
                (worker_id, now_vn_iso(), row["id"]))
            conn.commit()
            return dict(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def mark_done(self, item_id: int) -> None:
        self._set_status(item_id, "done", done=True)

    def mark_failed(self, item_id: int, error: str = "") -> None:
        self._set_status(item_id, "failed", error=error)

    def _set_status(self, item_id: int, status: str, *, done: bool = False,
                    error: str = "") -> None:
        conn = self.store.connect()
        try:
            conn.execute(
                "UPDATE work_items SET status=?, done_at=?, error=? WHERE id=?",
                (status, now_vn_iso() if done else None, error or None, item_id))
            conn.commit()
        finally:
            conn.close()

    def counts(self) -> dict[str, int]:
        conn = self.store.connect()
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) n FROM work_items GROUP BY status").fetchall()
            return {r["status"]: r["n"] for r in rows}
        finally:
            conn.close()
