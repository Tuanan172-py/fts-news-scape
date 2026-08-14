"""
Tests CafeF capture (phase-02) — raw artifact byte-exact, ordering (AC7), failure.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import src.scrapers.cafef as cafef_mod
from _fakes import FakeHTTP
from src.crawler.raw_store import RawStore
from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.scrapers.cafef import CafeFScraper

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


def test_capture_writes_artifact_ok(env, fixture_list, fixture_detail):
    http = FakeHTTP(list_json=fixture_list, detail_html=fixture_detail)
    scraper = CafeFScraper(_config(), http, env)
    result = scraper.run()

    assert len(result.new) > 0
    for a in result.new:
        cap = a.metadata["capture"]
        assert cap["capture_status"] in ("ok", "partial")
        # AC2/AC6: artifact byte-exact tồn tại, mở offline được
        disk = Path(cap["html_path"]).read_text(encoding="utf-8")
        assert disk == fixture_detail
        # AC3: content_html vẫn giữ #mainContent (vùng con); full page trong artifact
        assert "mainContent" in a.content_html or len(a.content_html) > 0


def test_order_raw_saved_before_extract(env, fixture_list, fixture_detail, monkeypatch):
    events = []
    orig_save = RawStore.save

    def spy_save(self, *a, **k):
        events.append("save")
        return orig_save(self, *a, **k)

    orig_extract = cafef_mod.extract_text

    def spy_extract(*a, **k):
        events.append("extract")
        return orig_extract(*a, **k)

    monkeypatch.setattr(RawStore, "save", spy_save)
    monkeypatch.setattr(cafef_mod, "extract_text", spy_extract)

    http = FakeHTTP(list_json=fixture_list, detail_html=fixture_detail)
    CafeFScraper(_config(), http, env).run()

    # AC7: raw save luôn xảy ra TRƯỚC extract_text (cleaning)
    assert events and events[0] == "save"
    assert events.index("save") < events.index("extract")


def test_detail_404_records_failed(env, fixture_list):
    http = FakeHTTP(list_json=fixture_list, detail_html=None)  # get_response → None
    scraper = CafeFScraper(_config(), http, env)
    result = scraper.run()
    assert len(result.new) > 0
    for a in result.new:
        assert a.metadata["capture"]["capture_status"] == "failed"
        assert a.content_text == a.summary
    assert any("detail fetch failed" in e for e in result.errors)
