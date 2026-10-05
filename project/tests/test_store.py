"""
Tests cho ArticleStore (schema v2, WAL) + DBWriter (single-writer queue).
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.core.models import Article
from src.db.store import ArticleStore
from src.db.writer import DBWriter


@pytest.fixture
def store(tmp_path):
    return ArticleStore(db_path=str(tmp_path / "test.db"))


def _article(url="https://ex.com/a", title="Bài A", domain="ex.com") -> Article:
    return Article(url=url, title=title, source_domain=domain,
                   summary="tóm tắt", content_html="<p>Nội dung</p>",
                   content_text="Nội dung", published_at="2026-07-24T09:00:00+07:00")


def test_wal_mode_active(store):
    conn = store._connect()
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode.lower() == "wal"


def test_insert_and_unique_conflict_ignored(store):
    a = _article()
    assert store.insert(a) is True
    # Trùng URL → bỏ qua, không raise, không ghi đè
    assert store.insert(a) is False
    assert store.count() == 1


def test_raw_html_and_text_roundtrip(store):
    a = _article()
    a.symbols = ["HPG", "VNM"]
    a.metadata = {"feed_name": "Test Feed"}
    store.insert(a)
    got = store.get_recent(limit=1)[0]
    assert got.content_html == "<p>Nội dung</p>"
    assert got.content_text == "Nội dung"
    assert got.symbols == ["HPG", "VNM"]
    assert got.metadata == {"feed_name": "Test Feed"}


def test_count_by_domain(store):
    store.insert(_article("https://ex.com/1", "T1"))
    store.insert(_article("https://other.com/2", "T2", domain="other.com"))
    counts = store.count_by_domain(since_iso="")
    assert counts == {"ex.com": 1, "other.com": 1}


def test_writer_flush_on_stop(store):
    writer = DBWriter(store, flush_interval=0.2)
    for i in range(120):  # > batch_size để test nhiều batch
        writer.enqueue(_article(f"https://ex.com/{i}", f"Title {i}"))
    writer.stop()
    assert writer.inserted == 120
    assert store.count() == 120


def test_writer_dedup_at_db_level(store):
    writer = DBWriter(store, flush_interval=0.2)
    a = _article()
    writer.enqueue(a)
    writer.enqueue(a)  # duplicate trong cùng batch
    writer.stop()
    assert store.count() == 1
