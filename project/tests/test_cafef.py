"""
Tests cho CafeFScraper — fixture thật (captured 2026-07-24), mock HTTPClient.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from _fakes import FakeHTTP
from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.scrapers.cafef import CafeFScraper, parse_cafef_date

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_list():
    return json.loads((FIXTURES / "cafef_list_response.json").read_text(encoding="utf-8"))


@pytest.fixture
def fixture_detail():
    return (FIXTURES / "cafef_detail_page.html").read_text(encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # cô lập RawStore ghi data/raw_html vào tmp
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    dedup = DedupCache(store, legacy_json_path="")
    yield dedup
    dedup.close()


def _config(**over):
    cfg = {
        "name": "cafef", "enabled": True, "timeout": 30,
        "api": {"params": {"Newstype": 0, "PageIndex": 1, "PageSize": 5, "Type": 1}},
        "detail": {"content_selector": "div#mainContent", "max_details_per_cycle": 30},
        "watchlist": ["FPT"],
    }
    cfg.update(over)
    return cfg


# ---- parse_cafef_date --------------------------------------------------------

def test_parse_date_no_tz():
    iso = parse_cafef_date("/Date(1784543714000)/")
    assert iso is not None and iso.endswith("+07:00")


def test_parse_date_with_tz():
    assert parse_cafef_date("/Date(1770108462000+0700)/") is not None


def test_parse_date_malformed():
    assert parse_cafef_date("not a date") is None
    assert parse_cafef_date("") is None
    assert parse_cafef_date(None) is None


# ---- scraper -----------------------------------------------------------------

def test_happy_path_real_fixture(env, fixture_list, fixture_detail):
    http = FakeHTTP(list_json=fixture_list, detail_html=fixture_detail)
    scraper = CafeFScraper(_config(), http, env)
    result = scraper.run()

    assert result.fetched == len(fixture_list["Data"])
    assert len(result.new) == result.fetched
    for a in result.new:
        assert a.url.startswith("https://cafef.vn/")
        assert a.title
        assert a.source_domain == "cafef.vn"
        assert a.symbols == ["FPT"]
        assert a.published_at.endswith("+07:00")
        # raw HTML bảo toàn + text sạch
        assert "mainContent" in a.content_html or len(a.content_html) > 0
        assert len(a.content_text) > 0


def test_dedup_second_run_zero_new(env, fixture_list, fixture_detail):
    http = FakeHTTP(list_json=fixture_list, detail_html=fixture_detail)
    scraper = CafeFScraper(_config(), http, env)
    assert len(scraper.run().new) > 0
    assert len(scraper.run().new) == 0


def test_empty_response_no_crash(env):
    http = FakeHTTP(list_json={"Data": None, "Success": False,
                               "Message": "loại tin khoán trống"})
    scraper = CafeFScraper(_config(), http, env)
    result = scraper.run()
    assert result.fetched == 0
    assert result.new == []


def test_list_fetch_failure_one_symbol_continues(env, fixture_list):
    class FlakyHTTP(FakeHTTP):
        def __init__(self, list_json):
            super().__init__(list_json=list_json)
            self.calls = 0

        def get_json(self, url, **kw):
            self.calls += 1
            return None if self.calls == 1 else self.list_json

    http = FlakyHTTP(fixture_list)
    scraper = CafeFScraper(_config(watchlist=["AAA", "FPT"]), http, env)
    result = scraper.run()
    # symbol 1 fail → error ghi nhận, symbol 2 vẫn chạy
    assert any("AAA" in e for e in result.errors)
    assert result.fetched == len(fixture_list["Data"])


def test_detail_404_keeps_summary(env, fixture_list):
    http = FakeHTTP(list_json=fixture_list, detail_html=None)  # get → None
    scraper = CafeFScraper(_config(), http, env)
    result = scraper.run()
    assert len(result.new) > 0
    for a in result.new:
        assert a.content_text == a.summary  # fallback
    assert any("detail fetch failed" in e for e in result.errors)


def test_detail_cap_defers(env, fixture_list, fixture_detail):
    http = FakeHTTP(list_json=fixture_list, detail_html=fixture_detail)
    cfg = _config()
    cfg["detail"]["max_details_per_cycle"] = 1
    scraper = CafeFScraper(cfg, http, env)
    result = scraper.run()
    assert http.detail_calls == 1
    deferred = [a for a in result.new if a.metadata.get("detail_deferred")]
    assert len(deferred) == len(result.new) - 1
    for a in deferred:
        assert a.content_text == a.summary


def test_selector_miss_preserves_body(env, fixture_list):
    # selector #mainContent miss → D5 density fallback (hoặc full page) cho content_html;
    # raw artifact vẫn được lưu byte-exact (kiểm ở test_cafef_capture).
    http = FakeHTTP(list_json=fixture_list,
                    detail_html="<html><body><p>Nội dung bài viết dài.</p></body></html>")
    scraper = CafeFScraper(_config(), http, env)
    result = scraper.run()
    for a in result.new:
        assert "Nội dung bài viết" in a.content_html  # body được giữ
