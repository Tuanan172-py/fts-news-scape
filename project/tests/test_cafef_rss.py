"""
CafeF hybrid: nhánh RSS per-category (bổ sung API symbol-driven) — bắt tin không gắn mã CK.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from _fakes import FakeHTTP
from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.scrapers.cafef import CafeFScraper

_RSS = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>CafeF Vi mo</title>
<item>
  <title>Vi mo: CPI thang 8 tang manh</title>
  <link>https://cafef.vn/vi-mo-cpi-thang-8.chn</link>
  <description>Chi so gia tieu dung thang 8 tang.</description>
  <pubDate>Mon, 18 Aug 2026 08:00:00 +0700</pubDate>
</item>
</channel></rss>"""

_DETAIL = ("<html><body><div id='mainContent'><p>"
           + "Noi dung vi mo day du ve chi so gia. " * 60
           + "</p></div></body></html>")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    dedup = DedupCache(store, legacy_json_path="")
    yield dedup
    dedup.close()


def _config(**over):
    cfg = {
        "name": "cafef", "enabled": True, "timeout": 30,
        "api": {"params": {"Type": 1}},
        "detail": {"content_selector": "div#mainContent", "max_details_per_cycle": 30},
        "watchlist": [],  # bỏ API symbol-driven → chỉ test nhánh RSS
        "rss": {"feeds": [{"url": "https://cafef.vn/vi-mo-dau-tu.rss", "name": "CafeF Vĩ mô"}]},
        "compliance": {"respect_robots": False},
    }
    cfg.update(over)
    return cfg


def test_cafef_rss_branch_captures(env):
    http = FakeHTTP(feed_bytes=_RSS, detail_html=_DETAIL)
    scraper = CafeFScraper(_config(), http, env)
    result = scraper.run()

    assert len(result.new) == 1
    a = result.new[0]
    assert a.source_domain == "cafef.vn"
    assert a.categories == ["CafeF Vĩ mô"]           # gắn nhãn chuyên mục
    assert a.url.startswith("https://cafef.vn/")
    assert a.metadata["capture"]["capture_status"] in ("ok", "partial")  # raw đã lưu


def test_cafef_no_rss_when_feeds_absent(env):
    # Không có rss.feeds → chỉ chạy API như cũ (watchlist rỗng → 0 bài), không lỗi.
    http = FakeHTTP(list_json={"Data": []}, detail_html=_DETAIL)
    scraper = CafeFScraper(_config(rss={}), http, env)
    result = scraper.run()
    assert result.new == []
