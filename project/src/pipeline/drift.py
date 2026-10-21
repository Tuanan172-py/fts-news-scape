"""Query articles in TEMPLATE_DRIFT or SELECTOR_BROKEN state from the article_versions table for drift reporting."""

from __future__ import annotations

_HELD_STATES = ("TEMPLATE_DRIFT", "SELECTOR_BROKEN")


def list_drift(store, limit: int = 100) -> list[dict]:
    """List articles with a layout drift or a broken selector.

    Args:
        store: ArticleStore object connected to the database.
        limit: Maximum number of records to fetch.

    Returns:
        One dict per article affected by drift.
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
