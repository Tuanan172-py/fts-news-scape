"""Tests cho đường requeue các trạng thái kẹt — Phase 03 & US-018.

Hai trạng thái ngõ cụt:
1. `held` (work_items): tự động nâng về `pending` khi re-derive thành công.
2. `claimed` (work_items): scheduler job `reclaim_stale` nhả về `pending` sau timeout.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from src.core.models import now_vn_iso
from src.db.store import ArticleStore
from src.handoff.catalog import Catalog



@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = str(tmp_path / "test_requeue.db")
    store = ArticleStore(db_path=db)
    catalog = Catalog(store)
    return store, catalog, db


def test_held_upsert_to_pending_when_valid(env):
    """Khi bài trước đó bị held, enqueue mới có trạng thái pending phải cứu bài về pending."""
    store, catalog, _db = env
    aid = "hash_held_01"
    sha = "sha_held_01"

    # Enqueue đầu tiên bị held (ví dụ selector broken)
    st1 = catalog.enqueue(aid, sha, "cafef.vn", "pkg1.json", "NEW", force_held=True)
    assert st1 == "held"

    # Derive lại thành công (force_held=False, change_state='NEW')
    st2 = catalog.enqueue(aid, sha, "cafef.vn", "pkg1.json", "NEW", force_held=False)
    assert st2 == "pending"

    conn = store.connect()
    row = conn.execute("SELECT status FROM work_items WHERE article_id=?", (aid,)).fetchone()
    conn.close()
    assert row["status"] == "pending"


def test_reclaim_stale_only_reclaims_expired_claimed(env, monkeypatch):
    """reclaim_stale chỉ nhả claimed quá hạn, không đụng vào claimed mới."""
    store, catalog, _db = env
    aid1 = "art_claimed_old"
    aid2 = "art_claimed_new"

    conn = store.connect()
    conn.execute(
        "INSERT INTO work_items (article_id, raw_sha256, domain, package_path, status, claimed_by, claimed_at, enqueued_at) "
        "VALUES (?, ?, 'a.vn', 'p.json', 'claimed', 'worker1', '2026-09-17T10:00:00+07:00', '2026-09-17T09:00:00+07:00')",
        (aid1, "sha1")
    )
    conn.execute(
        "INSERT INTO work_items (article_id, raw_sha256, domain, package_path, status, claimed_by, claimed_at, enqueued_at) "
        "VALUES (?, ?, 'a.vn', 'p.json', 'claimed', 'worker2', ?, ?)",
        (aid2, "sha2", now_vn_iso(), now_vn_iso())
    )
    conn.commit()
    conn.close()

    # Reclaim với timeout 60 phút
    reclaimed = catalog.reclaim_stale(timeout_minutes=60)
    assert reclaimed == 1

    conn = store.connect()
    r1 = conn.execute("SELECT status, claimed_by FROM work_items WHERE article_id=?", (aid1,)).fetchone()
    r2 = conn.execute("SELECT status, claimed_by FROM work_items WHERE article_id=?", (aid2,)).fetchone()
    conn.close()

    assert r1["status"] == "pending"
    assert r1["claimed_by"] is None
    assert r2["status"] == "claimed"
    assert r2["claimed_by"] == "worker2"
