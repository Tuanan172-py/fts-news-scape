"""
Tests cho DedupCache (SQLite-backed, bảng seen_articles).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.db.dedup import DedupCache, normalize_title
from src.db.store import ArticleStore


@pytest.fixture
def store(tmp_path):
    return ArticleStore(db_path=str(tmp_path / "t.db"))


def test_dedup_basic(store):
    cache = DedupCache(store, legacy_json_path="")
    assert not cache.is_duplicate("https://ex.com/a", "Title A")
    cache.mark_seen("https://ex.com/a", "Title A", "ex.com")
    assert cache.is_duplicate("https://ex.com/a", "Title A")
    assert not cache.is_duplicate("https://ex.com/b", "Title B")
    cache.close()


def test_dedup_persistence(store):
    cache = DedupCache(store, legacy_json_path="")
    cache.mark_seen("https://ex.com/x", "Title X", "ex.com")
    cache.close()

    cache2 = DedupCache(store, legacy_json_path="")
    assert cache2.is_duplicate("https://ex.com/x", "Title X")
    assert cache2.count() == 1
    cache2.close()


def test_legacy_json_migration(store, tmp_path):
    legacy = tmp_path / "dedup_cache.json"
    legacy.write_text(json.dumps({"a" * 64: 1700000000.0, "b" * 64: 1700000001.0}))

    cache = DedupCache(store, legacy_json_path=str(legacy))
    assert cache.count() == 2
    assert not legacy.exists()  # file xoá sau migration
    cache.close()


def test_recent_titles_excludes_own_domain(store):
    cache = DedupCache(store, legacy_json_path="")
    cache.mark_seen("https://a.com/1", "Tin HPG tăng trần", "a.com")
    cache.mark_seen("https://b.com/1", "Tin VNM giảm sàn", "b.com")
    titles = cache.recent_titles(hours=1, exclude_domain="a.com")
    assert titles == [(normalize_title("Tin VNM giảm sàn"), "b.com")]
    cache.close()


def test_normalize_title():
    assert normalize_title("  Tin   HPG\tTăng ") == "tin hpg tăng"
