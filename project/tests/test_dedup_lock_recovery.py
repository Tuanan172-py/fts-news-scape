"""Regression: one `database is locked` on the dedup connection must not stall capture.

Incident 2026-11-17: a long write by another process made `DedupCache.discover` fail at
15:43. The deferred transaction stayed open, the next read pinned a WAL snapshot, and every
later write failed at once with SQLITE_BUSY_SNAPSHOT, so no article was captured until the
process restarted. Each cycle died without a log line because the error escaped run_cycle.
"""

from __future__ import annotations

import sqlite3

import pytest

from src.db.dedup import DedupCache
from src.db.store import ArticleStore


@pytest.fixture
def cache(tmp_path):
    db = tmp_path / "m.db"
    dc = DedupCache(ArticleStore(str(db)), legacy_json_path="")
    dc._conn.execute("PRAGMA busy_timeout=200")
    yield dc, db
    dc.close()


def _foreign_commit(db) -> None:
    w = sqlite3.connect(db)
    w.execute("CREATE TABLE IF NOT EXISTS _t (x)")
    w.execute("INSERT INTO _t VALUES (1)")
    w.commit()
    w.close()


def test_failed_write_leaves_no_open_transaction(cache):
    dc, db = cache
    other = sqlite3.connect(db, timeout=1)
    other.execute("BEGIN IMMEDIATE")
    with pytest.raises(sqlite3.OperationalError):
        dc.discover("https://a.vn/x-1.html", "a.vn")
    assert not dc._conn.in_transaction
    other.execute("COMMIT")
    other.close()


def test_capture_recovers_after_lock_and_foreign_commits(cache):
    dc, db = cache
    other = sqlite3.connect(db, timeout=1)
    other.execute("BEGIN IMMEDIATE")
    with pytest.raises(sqlite3.OperationalError):
        dc.discover("https://a.vn/x-1.html", "a.vn")
    other.execute("COMMIT")
    other.close()
    for i in range(3):
        dc.known_keys(["k"])          # read, as pagination does before discovery
        _foreign_commit(db)           # the daemon and the DB writer commit meanwhile
        key, is_new, _ = dc.discover(f"https://a.vn/y-{i}.html", "a.vn")
        assert key and is_new


def test_stale_transaction_from_elsewhere_is_cleared(cache):
    dc, db = cache
    dc._conn.execute("BEGIN")
    dc._conn.execute("SELECT count(*) FROM seen_articles").fetchone()
    _foreign_commit(db)
    dc.mark_seen("https://a.vn/z.html", "Tiêu đề", "a.vn")
    assert dc.is_duplicate("https://a.vn/z.html", "Tiêu đề")
