"""Trợ thủ truy vấn và báo cáo độ lệch cấu trúc (Drift Report Helper).

Cung cấp hàm list_drift để trích xuất danh sách các bài viết gặp lỗi
TEMPLATE_DRIFT hoặc SELECTOR_BROKEN trong bảng article_versions.
"""

from __future__ import annotations

_HELD_STATES = ("TEMPLATE_DRIFT", "SELECTOR_BROKEN")


def list_drift(store, limit: int = 100) -> list[dict]:
    """Lấy danh sách các bài viết bị lệch giao diện hoặc hỏng selector.

    Args:
        store: Đối tượng ArticleStore kết nối cơ sở dữ liệu.
        limit: Số lượng bản ghi tối đa cần lấy.

    Returns:
        Danh sách từ điển chứa thông tin các bài viết gặp sự cố drift.
    """
    conn = store.connect()
    try:
        rows = conn.execute(
            "SELECT url_title_hash, source_domain, captured_at, state, recommendation "
            "FROM article_versions WHERE state IN ('TEMPLATE_DRIFT','SELECTOR_BROKEN') "
            "ORDER BY captured_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
