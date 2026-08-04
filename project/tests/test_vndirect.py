"""
Tests VndirectScraper — fixture thật (captured 2026-07-25), mock HTTP.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.scrapers.vndirect import VndirectScraper

FIXTURES = Path(__file__).parent / "fixtures"


class FakeHTTP:
    def __init__(self, payload, detail_html=None):
        self.payload = payload
        self.detail_html = detail_html
        self.detail_calls = 0

    def get_json(self, url, **kw):
        return self.payload

    def get(self, url, **kw):
        # fallback fetch bài gốc khi content rỗng/ngắn
        self.detail_calls += 1
        return self.detail_html


@pytest.fixture
def dedup(tmp_path):
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    d = DedupCache(store, legacy_json_path="")
    yield d
    d.close()


@pytest.fixture
def fixture_news():
    return json.loads((FIXTURES / "vndirect_news.json").read_text(encoding="utf-8"))


def _config(**over):
    cfg = {"name": "vndirect", "enabled": True, "timeout": 30,
           "api": {"page_size": 5}}
    cfg.update(over)
    return cfg


def test_happy_path_real_fixture(dedup, fixture_news):
    scraper = VndirectScraper(_config(), FakeHTTP(fixture_news), dedup)
    result = scraper.run()
    assert result.fetched == len(fixture_news["data"])
    assert len(result.new) == result.fetched
    for a in result.new:
        assert a.title and a.url.startswith("http")
        assert a.source_domain == "vndirect.com.vn"
        assert a.published_at.endswith("+07:00")
        assert a.metadata["news_source"]
        # full content từ list response, không cần detail fetch
        assert len(a.content_html) > 100
        assert len(a.content_text) > 50
        assert "_content_html" not in a.metadata  # đã pop trong enrich


def test_api_failure_no_crash(dedup):
    scraper = VndirectScraper(_config(), FakeHTTP(None), dedup)
    result = scraper.run()
    assert result.new == []
    assert any("fetch failed" in e for e in result.errors)


def test_item_without_url_skipped(dedup, fixture_news):
    fixture_news["data"][0]["newsUrl"] = ""
    fixture_news["data"][0]["dstockUrl"] = ""
    scraper = VndirectScraper(_config(), FakeHTTP(fixture_news), dedup)
    result = scraper.run()
    assert len(result.new) == len(fixture_news["data"]) - 1


def test_dedup_second_run(dedup, fixture_news):
    scraper = VndirectScraper(_config(), FakeHTTP(fixture_news), dedup)
    assert len(scraper.run().new) > 0
    assert len(scraper.run().new) == 0


def test_empty_content_fetches_origin_then_falls_back(dedup, fixture_news):
    for item in fixture_news["data"]:
        item["newsContent"] = ""
    # origin fetch fail (None) → fallback abstract
    http = FakeHTTP(fixture_news, detail_html=None)
    scraper = VndirectScraper(_config(), http, dedup)
    result = scraper.run()
    assert http.detail_calls == len(result.new)  # đã thử fetch bài gốc
    for a in result.new:
        assert a.content_text == a.summary


def test_empty_content_origin_fetch_success(dedup, fixture_news):
    for item in fixture_news["data"]:
        item["newsContent"] = ""
    origin = ("<html><body><article><p>" + "Nội dung đầy đủ từ báo gốc. " * 20
              + "</p></article></body></html>")
    scraper = VndirectScraper(_config(), FakeHTTP(fixture_news, detail_html=origin), dedup)
    result = scraper.run()
    for a in result.new:
        assert "Nội dung đầy đủ từ báo gốc" in a.content_text


