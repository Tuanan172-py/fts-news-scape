"""
Tests VnEconomyScraper — RSS list + full raw HTML capture (parity vietstock).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from _fakes import FakeHTTP
from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.scrapers import REGISTRY
from src.scrapers.vneconomy import VnEconomyScraper

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def feed_bytes():
    return (FIXTURES / "vneconomy_capture_feed.xml").read_bytes()


@pytest.fixture
def detail_html():
    return (FIXTURES / "vneconomy_detail_page.html").read_text(encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # cô lập RawStore ghi data/raw_html vào tmp
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    dedup = DedupCache(store, legacy_json_path="")
    yield dedup
    dedup.close()


def _config(**over):
    cfg = {
        "name": "vneconomy", "enabled": True, "timeout": 30, "language": "vi",
        "rss": {"feeds": [{"url": "https://vneconomy.vn/chung-khoan.rss",
                           "name": "VnEconomy Chứng khoán"}]},
        "detail": {"content_selector": "#article-editor",
                   "max_details_per_cycle": 30},
        "watchlist": ["TCB", "FPT", "VNM"],
    }
    cfg.update(over)
    return cfg


def test_registered():
    assert "vneconomy" in REGISTRY
    assert REGISTRY["vneconomy"] is VnEconomyScraper


def test_capture_happy_path(env, feed_bytes, detail_html):
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=detail_html)
    scraper = VnEconomyScraper(_config(), http, env)
    result = scraper.run()

    assert len(result.new) > 0
    captured = [a for a in result.new
                if a.metadata.get("capture", {}).get("capture_status") == "ok"]
    assert captured, "ít nhất 1 bài capture ok"
    a = captured[0]
    assert a.source_domain == "vneconomy.vn"
    assert a.published_at.endswith("+07:00")
    assert a.metadata["language"] == "vi"
    # artifact byte-exact (raw không bị mutate)
    assert Path(a.metadata["capture"]["html_path"]).read_text(encoding="utf-8") == detail_html
    # container #article-editor → content_html non-empty
    assert len(a.content_html) > 0
    # content_text trích được từ body (không rỗng, khác summary ngắn)
    assert len(a.content_text) > 0
    # image manifest: ảnh bài trên CDN premedia (src trực tiếp, không lazy)
    imgs = a.metadata["capture"]["images"]
    assert any("premedia.vneconomy.vn" in (i["resolved_url"] or "") for i in imgs)


def test_tickers_tagged(env, feed_bytes, detail_html):
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=detail_html)
    result = VnEconomyScraper(_config(), http, env).run()
    # bài "Đua bán tháo..." có TCB trong title/summary
    assert any("TCB" in a.symbols for a in result.new)


def test_detail_failure_keeps_summary(env, feed_bytes):
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=None)  # get_response → None
    result = VnEconomyScraper(_config(), http, env).run()
    assert len(result.new) > 0
    for a in result.new:
        assert a.metadata["capture"]["capture_status"] == "failed"
        assert a.content_text == a.summary
    assert any("detail fetch failed" in e for e in result.errors)
