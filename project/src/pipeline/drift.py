"""
Drift report helper — liệt kê bài bị TEMPLATE_DRIFT / SELECTOR_BROKEN (phase-02).

Dùng chung cho `scripts/report_drift.py` (CLI) và `src/morninger.py` (job hằng ngày).
Producer xem danh sách này để sửa selector/extractor TRƯỚC khi agent tiêu thụ package hỏng.
"""

from __future__ import annotations

_HELD_STATES = ("TEMPLATE_DRIFT", "SELECTOR_BROKEN")


def list_drift(store, limit: int = 100) -> list[dict]:
    """Trả danh sách bài drift/broken, mới nhất trước."""
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
