"""
Tests VietstockScraper (phase-03) — RSS list + full raw HTML capture.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from _fakes import FakeHTTP
from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.scrapers import REGISTRY
from src.scrapers.vietstock import VietstockScraper

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def feed_bytes():
    return (FIXTURES / "vietstock_feed.xml").read_bytes()


@pytest.fixture
def detail_html():
    return (FIXTURES / "vietstock_detail_page.html").read_text(encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # cô lập RawStore ghi data/raw_html vào tmp
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    dedup = DedupCache(store, legacy_json_path="")
    yield dedup
    dedup.close()


def _config(**over):
    cfg = {
        "name": "vietstock", "enabled": True, "timeout": 30, "language": "vi",
        "rss": {"feeds": [{"url": "https://vietstock.vn/144/chung-khoan.rss",
                           "name": "Vietstock Chứng khoán"}]},
        "detail": {"content_selector": "div.article-content, article",
                   "max_details_per_cycle": 30},
        "watchlist": ["FPT", "MBB", "VNM"],
    }
    cfg.update(over)
    return cfg


def test_registered():
    assert "vietstock" in REGISTRY
    assert REGISTRY["vietstock"] is VietstockScraper


def test_capture_happy_path(env, feed_bytes, detail_html):
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=detail_html)
    scraper = VietstockScraper(_config(), http, env)
    result = scraper.run()

    assert len(result.new) > 0
    captured = [a for a in result.new
                if a.metadata.get("capture", {}).get("capture_status") == "ok"]
    assert captured, "ít nhất 1 bài capture ok"
    a = captured[0]
    assert a.source_domain == "vietstock.vn"
    assert a.published_at.endswith("+07:00")
    assert a.metadata["language"] == "vi"
    # AC2/AC6: artifact byte-exact
    assert Path(a.metadata["capture"]["html_path"]).read_text(encoding="utf-8") == detail_html
    # AC3: container thành content_html
    assert "article-content" in a.content_html or len(a.content_html) > 0
    # AC5: image manifest có ảnh lazy resolved
    imgs = a.metadata["capture"]["images"]
    assert any("Down-8" in (i["resolved_url"] or "") for i in imgs)


def test_tickers_tagged(env, feed_bytes, detail_html):
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=detail_html)
    result = VietstockScraper(_config(), http, env).run()
    # bài "10 cổ phiếu nóng" có FPT trong description
    assert any("FPT" in a.symbols for a in result.new)


def test_detail_failure_keeps_summary(env, feed_bytes):
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=None)  # get_response → None
    result = VietstockScraper(_config(), http, env).run()
    assert len(result.new) > 0
    for a in result.new:
        assert a.metadata["capture"]["capture_status"] == "failed"
        assert a.content_text == a.summary
    assert any("detail fetch failed" in e for e in result.errors)
