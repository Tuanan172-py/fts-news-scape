"""
Tests cho BaseScraper template method: dedup skip, error resilience.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.core.base_scraper import BaseScraper
from src.core.models import Article
from src.db.dedup import DedupCache
from src.db.store import ArticleStore


class DummyScraper(BaseScraper):
    """Scraper giả lập — không network."""

    def fetch_list(self):
        return [
            {"url": "https://d.com/1", "title": "Bài 1"},
            {"url": "https://d.com/2", "title": "Bài 2"},
            {"url": "BAD"},  # thiếu title → parse_item raise
        ]

    def parse_item(self, raw):
        return Article(url=raw["url"], title=raw["title"], source_domain="d.com",
                       summary="s")

    def enrich(self, article):
        article.content_html = f"<p>{article.title}</p>"
        article.content_text = article.title


@pytest.fixture
def env(tmp_path):
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    dedup = DedupCache(store, legacy_json_path="")
    yield store, dedup
    dedup.close()


def _make(env, cls=DummyScraper, config=None):
    store, dedup = env
    return cls(config or {"name": "dummy", "enabled": True}, http=None, dedup=dedup)


def test_run_happy_path_with_parse_error(env):
    scraper = _make(env)
    result = scraper.run()
    # 3 raw items, 1 parse lỗi → 2 article mới; lỗi được gom không crash
    assert result.fetched == 3
    assert len(result.new) == 2
    assert len(result.errors) == 1
    assert result.new[0].content_html == "<p>Bài 1</p>"
    assert result.new[0].processed_at != ""


def test_run_dedup_skips_seen(env):
    """Dedup có hiệu lực SAU khi bài được ghi bền vững vào `articles`, không phải lúc cào.

    Trước 2026-09-08 scraper tự mark_seen ngay trong run(), trước khi DBWriter ghi
    `articles`. Bất kỳ gián đoạn nào ở giữa khiến bài bị đánh dấu 'đã thấy' vĩnh viễn mà
    không có dòng `articles` — 429 bài mồ côi trên monocle.db, 429/429 nằm trong
    seen_articles. Nay `seen_articles` được ghi cùng transaction với `articles`
    (store.insert_batch), nên dedup chỉ chặn thứ đã thực sự lưu được — và bài ghi hụt sẽ
    được thử lại ở chu kỳ sau thay vì mất im lặng.
    """
    store, _ = env
    scraper = _make(env)
    first = scraper.run()
    assert len(first.new) == 2

    # chưa ghi DB -> vẫn coi là mới (có thể thử lại)
    assert len(scraper.run().new) == 2

    store.insert_batch(first.new)
    assert len(scraper.run().new) == 0


def test_disabled_scraper_returns_empty(env):
    scraper = _make(env, config={"name": "dummy", "enabled": False})
    result = scraper.run()
    assert result.fetched == 0 and result.new == []


class CrashingFetchScraper(DummyScraper):
    def fetch_list(self):
        raise RuntimeError("network down")


def test_fetch_crash_does_not_raise(env):
    scraper = _make(env, cls=CrashingFetchScraper)
    result = scraper.run()  # không được raise
    assert result.new == []
    assert any("fetch_list" in e for e in result.errors)


class FailingEnrichScraper(DummyScraper):
    def fetch_list(self):
        return [{"url": "https://d.com/9", "title": "Bài 9"}]

    def enrich(self, article):
        raise ValueError("detail page 404")


def test_enrich_failure_keeps_article(env):
    scraper = _make(env, cls=FailingEnrichScraper)
    result = scraper.run()
    # enrich fail → vẫn giữ article (fallback summary), lỗi được ghi nhận
    assert len(result.new) == 1
    assert any("enrich" in e for e in result.errors)
