"""Bộ quản lý danh mục công việc điều phối giữa pipeline và các agent.

Cung cấp lớp Catalog để ghi nhận, phân phối và theo dõi trạng thái thực thi
của các gói công việc trong bảng work_items.
"""

from __future__ import annotations

from loguru import logger

from src.core.models import now_vn_iso

_HELD_STATES = {"SELECTOR_BROKEN", "TEMPLATE_DRIFT"}
_CLAIM_TIMEOUT_MIN = 120


def _iso_minus_minutes(minutes: int) -> str:
    """Tính mốc thời gian ISO lùi lại số phút chỉ định theo múi giờ Việt Nam.

    Args:
        minutes: Số phút cần lùi lại từ thời điểm hiện tại.

    Returns:
        Chuỗi mốc thời gian chuẩn ISO 8601 múi giờ +07:00.
    """
    from datetime import datetime, timedelta
    from src.core.models import VN_TZ
    return (datetime.now(VN_TZ) - timedelta(minutes=minutes)).isoformat(timespec="seconds")


class Catalog:
    """Bộ điều phối trạng thái và phân phối các gói công việc (work_items).

    Attributes:
        store: Đối tượng kho lưu trữ ArticleStore kết nối cơ sở dữ liệu.
    """

    def __init__(self, store):
        self.store = store

    def enqueue(self, article_id: str, raw_sha256: str, domain: str,
                package_path: str, change_state: str, *, force_held: bool = False) -> str:
        """Đưa gói công việc vào hàng đợi xử lý của danh mục.

        Thực hiện chèn an toàn (INSERT OR IGNORE) đảm bảo tính lũy kế không trùng lặp.

        Args:
            article_id: Mã định danh bài viết.
            raw_sha256: Mã băm SHA-256 của nội dung thô tầng Bronze.
            domain: Tên miền nguồn của bài viết.
            package_path: Đường dẫn tệp tin gói công việc JSON.
            change_state: Trạng thái thay đổi của bài viết.
            force_held: Cờ bắt buộc chuyển trạng thái sang 'held' (tạm hoãn xử lý).

        Returns:
            Trạng thái hiện tại của gói công việc trong cơ sở dữ liệu.
        """
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
        """Thu hồi các gói công việc ở trạng thái 'claimed' quá hạn trở lại 'pending'.

        Args:
            timeout_minutes: Thời hạn chiếm giữ tối đa tính bằng phút trước khi thu hồi.

        Returns:
            Số lượng gói công việc đã được hoàn trả lại hàng đợi.
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
        """Liệt kê danh sách các gói công việc đang chờ xử lý.

        Args:
            limit: Số lượng bản ghi tối đa cần lấy.
            order: Thứ tự sắp xếp theo thời gian ('asc' hoặc 'desc').

        Returns:
            Danh sách từ điển chứa thông tin các gói công việc 'pending'.
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
        """Nhận độc quyền một gói công việc đang chờ để thực thi.

        Args:
            worker_id: Mã định danh tiến trình hoặc agent nhận việc.
            order: Thứ tự ưu tiên nhận việc ('asc' hoặc 'desc').
            require_l1: Cờ yêu cầu bài viết phải đạt chuẩn thẩm định L1 trước đó.
            allowed_article_ids: Tập mã bài viết được phép chọn.
            date: Lọc theo ngày cụ thể (định dạng 'YYYY-MM-DD' hoặc 'today').
            days: Lọc các bài viết trong khoảng số ngày gần nhất.

        Returns:
            Từ điển thông tin gói công việc được bàn giao, hoặc None nếu không có gói phù hợp.
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
                " WHERE l1.article_id = work_items.article_id AND l1.dod_pass = 1)"
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
        """Đánh dấu gói công việc đã hoàn thành xử lý thành công.

        Args:
            item_id: Mã định danh bản ghi công việc (khóa chính id).
        """
        self._set_status(item_id, "done", done=True)

    def mark_failed(self, item_id: int, error: str = "") -> None:
        """Đánh dấu gói công việc xử lý thất bại kèm lý do lỗi.

        Args:
            item_id: Mã định danh bản ghi công việc.
            error: Chuỗi thông báo lỗi chi tiết.
        """
        self._set_status(item_id, "failed", error=error)

    def _set_status(self, item_id: int, status: str, *, done: bool = False,
                    error: str = "") -> None:
        """Cập nhật trạng thái bản ghi công việc trong cơ sở dữ liệu."""
        conn = self.store.connect()
        try:
            conn.execute(
                "UPDATE work_items SET status=?, done_at=?, error=? WHERE id=?",
                (status, now_vn_iso() if done else None, error or None, item_id))
            conn.commit()
        finally:
            conn.close()

    def counts(self) -> dict[str, int]:
        """Thống kê tổng số lượng gói công việc theo từng trạng thái.

        Returns:
            Từ điển ánh xạ từ trạng thái ('pending', 'claimed', 'done', 'failed', 'held')
            sang số lượng bản ghi tương ứng.
        """
        conn = self.store.connect()
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) n FROM work_items GROUP BY status").fetchall()
            return {r["status"]: r["n"] for r in rows}
        finally:
            conn.close()
