"""Manage the work catalog that coordinates the pipeline and the agents by recording, dispatching and tracking work packages in the work_items table."""

from __future__ import annotations

from loguru import logger

from src.agent.contract.article_contract import analyzed_l1_sql
from src.core.models import now_vn_iso

_HELD_STATES = {"SELECTOR_BROKEN", "TEMPLATE_DRIFT"}
_CLAIM_TIMEOUT_MIN = 120


def _iso_minus_minutes(minutes: int) -> str:
    """Compute an ISO timestamp the given number of minutes in the past, in Vietnam time.

    Args:
        minutes: Number of minutes to go back from the current time.

    Returns:
        ISO 8601 timestamp with the +07:00 offset.
    """
    from datetime import datetime, timedelta
    from src.core.models import VN_TZ
    return (datetime.now(VN_TZ) - timedelta(minutes=minutes)).isoformat(timespec="seconds")


class Catalog:
    """Coordinate the state and dispatch of work packages (work_items).

    Attributes:
        store: ArticleStore object connected to the database.
    """

    def __init__(self, store):
        """Bind the catalog to a store.

        Args:
            store: ArticleStore object connected to the database.
        """
        self.store = store

    def enqueue(self, article_id: str, raw_sha256: str, domain: str,
                package_path: str, change_state: str, *, force_held: bool = False) -> str:
        """Put a work package into the catalog processing queue.

        Inserts safely (INSERT OR IGNORE) so repeated calls never create duplicates.

        Args:
            article_id: Article identifier.
            raw_sha256: SHA-256 hash of the raw Bronze content.
            domain: Source domain of the article.
            package_path: Path of the work package JSON file.
            change_state: Change state of the article.
            force_held: Force the status to 'held' (processing deferred).

        Returns:
            Current status of the work package in the database.
        """
        status = "held" if (force_held or change_state in _HELD_STATES) else "pending"
        conn = self.store.connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO work_items "
                "(article_id, raw_sha256, domain, package_path, status, change_state, enqueued_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (article_id, raw_sha256, domain, package_path, status, change_state, now_vn_iso()))
            # INSERT OR IGNORE alone makes 'held' permanent: after the root cause (schema
            # error, selector drift) is fixed and a re-derive succeeds, the old row would stay
            # 'held'. Promote it to 'pending' so the article is recovered.
            # No retry cap is needed: this branch runs only when a NEW derive really passed
            # validation (status computed as 'pending'), so there is no loop to bound.
            if status == "pending":
                conn.execute(
                    "UPDATE work_items SET status='pending', package_path=?, "
                    "change_state=? "
                    "WHERE article_id=? AND raw_sha256=? AND status='held'",
                    (package_path, change_state, article_id, raw_sha256))
            conn.commit()
            row = conn.execute(
                "SELECT status FROM work_items WHERE article_id=? AND raw_sha256=?",
                (article_id, raw_sha256)).fetchone()
            return row["status"] if row else status
        finally:
            conn.close()

    def requeue(self, state: str, limit: int = 100, *, dry_run: bool = True) -> int:
        """Return stuck work packages to the `pending` queue.

        Covers the `failed` state (DoD miss). By operating decision this group is retried only
        when an operator asks for it, because the cause usually lies in the article content
        rather than in a transient configuration error.

        Args:
            state: Source state to recover (`failed` or `held`).
            limit: Maximum number of rows to process per run.
            dry_run: Only count, do not write.

        Returns:
            Number of work packages moved (or that would be moved) to `pending`.

        Raises:
            ValueError: If `state` is neither `failed` nor `held`.
        """
        if state not in ("failed", "held"):
            raise ValueError(f"state phải là 'failed' hoặc 'held', nhận: {state!r}")
        conn = self.store.connect()
        try:
            ids = [r["id"] for r in conn.execute(
                "SELECT id FROM work_items WHERE status=? ORDER BY id LIMIT ?",
                (state, limit)).fetchall()]
            if not ids or dry_run:
                return len(ids)
            marks = ",".join("?" * len(ids))
            cur = conn.execute(
                f"UPDATE work_items SET status='pending', claimed_by=NULL, "
                f"claimed_at=NULL WHERE id IN ({marks})", ids)
            conn.commit()
            n = cur.rowcount or 0
        finally:
            conn.close()
        if n:
            logger.warning("[catalog] requeue {} work_item tu '{}' ve 'pending'", n, state)
        return n

    def count_by_status(self) -> dict[str, int]:
        """Count work packages per status for the radar.

        Returns:
            Mapping of status to the number of work packages.
        """
        conn = self.store.connect()
        try:
            return {r["status"]: r["n"] for r in conn.execute(
                "SELECT status, count(1) AS n FROM work_items GROUP BY status")}
        finally:
            conn.close()

    def reclaim_stale(self, timeout_minutes: int = _CLAIM_TIMEOUT_MIN) -> int:
        """Return work packages stuck in 'claimed' past the deadline to 'pending'.

        Args:
            timeout_minutes: Maximum claim time in minutes before reclaiming.

        Returns:
            Number of work packages returned to the queue.
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
        """List the work packages waiting for processing.

        Args:
            limit: Maximum number of records to fetch.
            order: Time sort order ('asc' or 'desc').

        Returns:
            One dict per 'pending' work package.
        """
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
              require_l1: bool = False,
              allowed_article_ids: set[str] | list[str] | None = None,
              date: str | None = None,
              days: int | None = None) -> dict | None:
        """Claim exclusively one waiting work package for execution.

        Args:
            worker_id: Identifier of the process or agent that takes the work.
            order: Claim priority order ('asc' or 'desc').
            require_l1: Require the article to have passed L1 validation earlier.
            allowed_article_ids: Article ids that may be selected.
            date: Filter by a specific date ('YYYY-MM-DD' or 'today').
            days: Filter articles within the most recent number of days.

        Returns:
            Dict describing the handed-over work package, or None when no package matches.
        """
        self.reclaim_stale()
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
                f" WHERE l1.article_id = work_items.article_id AND {analyzed_l1_sql('l1')})"
                if require_l1 else ""
            )
            if allowed_article_ids is not None:
                if not allowed_article_ids:
                    conn.commit()
                    return None
                conn.execute("CREATE TEMP TABLE IF NOT EXISTS _allowed_aids (aid TEXT PRIMARY KEY)")
                conn.execute("DELETE FROM _allowed_aids")
                conn.executemany("INSERT OR IGNORE INTO _allowed_aids VALUES (?)", [(aid,) for aid in allowed_article_ids])
                allowed_clause = " AND EXISTS (SELECT 1 FROM _allowed_aids aa WHERE aa.aid = work_items.article_id)"
            else:
                allowed_clause = ""

            date_clause = ""
            params: list = []
            if date and date != "all":
                from datetime import datetime
                from src.core.models import VN_TZ
                d_target = f"{datetime.now(VN_TZ):%Y-%m-%d}" if date == "today" else date
                date_clause = (
                    " AND EXISTS (SELECT 1 FROM articles a WHERE a.url_title_hash = work_items.article_id"
                    " AND substr(COALESCE(NULLIF(a.published_at, ''), a.fetched_at, work_items.enqueued_at), 1, 10) = ?)"
                )
                params.append(d_target)
            elif days and days > 0:
                from datetime import datetime, timedelta
                from src.core.models import VN_TZ
                cutoff = f"{datetime.now(VN_TZ) - timedelta(days=days):%Y-%m-%d}"
                date_clause = (
                    " AND EXISTS (SELECT 1 FROM articles a WHERE a.url_title_hash = work_items.article_id"
                    " AND substr(COALESCE(NULLIF(a.published_at, ''), a.fetched_at, work_items.enqueued_at), 1, 10) >= ?)"
                )
                params.append(cutoff)

            query = (
                f"SELECT * FROM work_items WHERE status='pending'"
                f"{l1_clause}{allowed_clause}{date_clause} {order_clause} LIMIT 1"
            )
            row = conn.execute(query, params).fetchone()

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
        """Mark a work package as processed successfully.

        Args:
            item_id: Work item record identifier (primary key id).
        """
        self._set_status(item_id, "done", done=True)

    def mark_failed(self, item_id: int, error: str = "") -> None:
        """Mark a work package as failed with the error reason.

        Args:
            item_id: Work item record identifier.
            error: Detailed error message.
        """
        self._set_status(item_id, "failed", error=error)

    def _set_status(self, item_id: int, status: str, *, done: bool = False,
                    error: str = "") -> None:
        """Update the status of a work item record in the database."""
        conn = self.store.connect()
        try:
            conn.execute(
                "UPDATE work_items SET status=?, done_at=?, error=? WHERE id=?",
                (status, now_vn_iso() if done else None, error or None, item_id))
            conn.commit()
        finally:
            conn.close()

    def counts(self) -> dict[str, int]:
        """Count the total work packages per status.

        Returns:
            Mapping of status ('pending', 'claimed', 'done', 'failed', 'held') to the
            matching record count.
        """
        conn = self.store.connect()
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) n FROM work_items GROUP BY status").fetchall()
            return {r["status"]: r["n"] for r in rows}
        finally:
            conn.close()
