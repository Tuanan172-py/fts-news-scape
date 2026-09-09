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

# Item o 'claimed' qua lau = worker da chet giua chung (thoat truoc khi mark_done/mark_failed).
# Khong co buoc nay thi claim() — vi chi doc status='pending' — se KHONG bao gio thay lai chung:
# do la ro ri vinh vien. Do tren monocle.db 2026-09-07: 304 item ket, tang deu theo ngay
# (exporter: 2, 20, 32, 20, 50, 180). Xem scripts/l1_backlog.py.
_CLAIM_TIMEOUT_MIN = 120


def _iso_minus_minutes(minutes: int) -> str:
    """Moc thoi gian ISO (gio VN) lui `minutes` phut — so sanh chuoi voi claimed_at."""
    from datetime import timedelta
    from src.core.models import VN_TZ
    from datetime import datetime
    return (datetime.now(VN_TZ) - timedelta(minutes=minutes)).isoformat(timespec="seconds")


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

    def reclaim_stale(self, timeout_minutes: int = _CLAIM_TIMEOUT_MIN) -> int:
        """Tra cac item `claimed` qua han ve `pending`. Tra so item da thu hoi.

        An toan khi worker that su con song: no se mark_done/mark_failed theo id nen trang thai
        cuoi cung van dung; xau nhat la mot item bi lam hai lan (ingest la idempotent theo
        UNIQUE(article_id, raw_sha256)).
        """
        cutoff = _iso_minus_minutes(timeout_minutes)
        conn = self.store.connect()
        try:
            cur = conn.execute(
                "UPDATE work_items SET status='pending', claimed_by=NULL, claimed_at=NULL "
                "WHERE status='claimed' AND (claimed_at IS NULL OR claimed_at < ?)", (cutoff,))
            conn.commit()
            n = cur.rowcount or 0
        finally:
            conn.close()
        if n:
            logger.warning("[catalog] thu hoi {} work_item ket o 'claimed' qua {} phut", n, timeout_minutes)
        return n

    def list_pending(self, limit: int = 50, order: str = "desc") -> list[dict]:
        conn = self.store.connect()
        try:
            order_clause = (
                "ORDER BY enqueued_at DESC, id DESC"
                if order.lower() == "desc"
                else "ORDER BY enqueued_at ASC, id ASC"
            )
            rows = conn.execute(
                f"SELECT * FROM work_items WHERE status='pending' {order_clause} LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def claim(self, worker_id: str, order: str = "desc", *,
              require_l1: bool = False) -> dict | None:
        """Claim 1 item pending → claimed (atomic). None nếu hết việc.

        require_l1=True: chỉ bốc bài đã có `l1_outputs.dod_pass=1`. Gold chạy TRƯỚC L1 thì
        packet không nhúng được `input.l1_entities` (rule 05 §2.5) và bài cũng không định
        tuyến được cho user nào (routing dựa entity của L1) → tốn token vô ích.
        """
        self.reclaim_stale()          # khong co buoc nay, item ket o 'claimed' bi ro ri vinh vien
        conn = self.store.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            order_clause = (
                "ORDER BY enqueued_at DESC, id DESC"
                if order.lower() == "desc"
                else "ORDER BY enqueued_at ASC, id ASC"
            )
            l1_clause = (
                " AND EXISTS (SELECT 1 FROM l1_outputs l1"
                " WHERE l1.article_id = work_items.article_id AND l1.dod_pass = 1)"
                if require_l1 else ""
            )
            row = conn.execute(
                f"SELECT * FROM work_items WHERE status='pending'{l1_clause} {order_clause} LIMIT 1"
            ).fetchone()
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
