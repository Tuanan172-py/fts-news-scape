"""
Tests TBTC (thoibaotaichinhvietnam.vn) — config-level trên RssCaptureScraper.

KHÔNG có scraper riêng: nguồn này chỉ là 1 file YAML chạy trên class generic
`rss_capture` của phase-01. Test ở đây bảo vệ chính bản config đó.

Fixtures thật: feed tải live, trang detail tái tạo TỪ BRONZE đã capture.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from _fakes import FakeHTTP
from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.scrapers.rss_capture import RssCaptureScraper

FIXTURES = Path(__file__).parent / "fixtures"
FEED_URL = "https://thoibaotaichinhvietnam.vn/rss_feed/"


@pytest.fixture
def feed_bytes():
    return (FIXTURES / "tbtc_capture_feed.xml").read_bytes()


@pytest.fixture
def detail_html():
    return (FIXTURES / "tbtc_detail_page.html").read_text(encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    dedup = DedupCache(store, legacy_json_path="")
    yield dedup
    dedup.close()


def _config(**over):
    """Phản chiếu config/domains/thoibaotaichinhvietnam.yaml."""
    cfg = {
        "name": "thoibaotaichinhvietnam", "enabled": True, "timeout": 30,
        "language": "vi",
        "base_url": "https://thoibaotaichinhvietnam.vn/",
        "rss": {"feeds": [{"url": FEED_URL, "name": "TBTC Tin mới"}]},
        "detail": {"content_selector": "div.article-detail-main",
                   "category_meta": "article:section",
                   "max_details_per_cycle": 40},
        "watchlist": ["FPT", "VNM"],
        "fuzzy_dedup": False,
    }
    cfg.update(over)
    return cfg


def _scraper(cfg, http, dedup):
    s = RssCaptureScraper(cfg, http, dedup)
    s.backoff = None
    return s


def test_config_file_matches_test_config():
    """Config thật phải khớp giả định của test (1 feed, selector, category_meta)."""
    import yaml
    p = Path(__file__).resolve().parent.parent / "config" / "domains" / \
        "thoibaotaichinhvietnam.yaml"
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert cfg["method"] == "rss_capture"
    assert cfg["enabled"] is True
    # ⚠️ ĐÚNG 1 feed — feed theo chuyên mục của TBTC là ẢO (trả cùng feed site-wide)
    assert len(cfg["rss"]["feeds"]) == 1
    assert cfg["rss"]["feeds"][0]["url"] == FEED_URL
    assert cfg["detail"]["content_selector"] == "div.article-detail-main"
    assert cfg["detail"]["category_meta"] == "article:section"
    assert cfg["compliance"]["respect_robots"] is True
    assert cfg["rate_limit"] >= 3.0


def test_capture_happy_path(env, feed_bytes, detail_html):
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=detail_html)
    result = _scraper(_config(), http, env).run()

    assert len(result.new) > 0
    captured = [a for a in result.new
                if a.metadata.get("capture", {}).get("capture_status") == "ok"]
    assert captured
    a = captured[0]
    assert a.source_domain == "thoibaotaichinhvietnam.vn"
    assert a.published_at.endswith("+07:00")
    assert a.metadata["language"] == "vi"
    cap = a.metadata["capture"]
    assert Path(cap["html_path"]).read_text(encoding="utf-8") == detail_html  # byte-exact
    assert cap["http_status"] == 200
    assert len(a.content_text) > 0


def test_content_selector_hits(env, feed_bytes, detail_html):
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=detail_html)
    result = _scraper(_config(), http, env).run()
    for a in result.new:
        cap = a.metadata["capture"]
        assert cap["capture_status"] == "ok"
        assert "main_content_node" not in cap.get("missing", [])
        assert "incomplete_render" not in cap.get("missing", [])


def test_real_category_from_meta(env, feed_bytes, detail_html):
    """Feed gộp chung → tên feed không phải chuyên mục. Chuyên mục thật lấy từ
    <meta property="article:section">, và phải đứng ĐẦU danh sách categories."""
    import re
    expected = re.search(r'article:section"\s+content="([^"]+)"', detail_html).group(1)
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=detail_html)
    result = _scraper(_config(), http, env).run()
    captured = [a for a in result.new
                if a.metadata["capture"]["capture_status"] == "ok"]
    assert captured
    a = captured[0]
    assert a.categories[0] == expected
    assert "TBTC Tin mới" in a.categories       # tên feed vẫn giữ làm nguồn gốc


def test_inline_not_used_when_capture_ok(env, feed_bytes, detail_html):
    """Feed CÓ content:encoded — nhưng Bronze phải đến từ trang detail, không phải inline."""
    assert b"content:encoded" in feed_bytes, "fixture phải giữ content:encoded"
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=detail_html)
    result = _scraper(_config(), http, env).run()
    a = [x for x in result.new
         if x.metadata["capture"]["capture_status"] == "ok"][0]
    assert Path(a.metadata["capture"]["html_path"]).read_text(encoding="utf-8") == detail_html
    assert "_inline_html" not in a.metadata
    assert http.detail_calls > 0, "phải fetch detail dù feed đã có content:encoded"


def test_detail_failure_falls_back_to_inline(env, feed_bytes):
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=None)
    result = _scraper(_config(), http, env).run()
    assert len(result.new) > 0
    for a in result.new:
        assert a.metadata["capture"]["capture_status"] == "failed"
        assert len(a.content_text) > 0        # inline content:encoded cứu body
    assert any("detail fetch failed" in e for e in result.errors)


def test_max_details_cap(env, feed_bytes, detail_html):
    cfg = _config(detail={"content_selector": "div.article-detail-main",
                          "category_meta": "article:section",
                          "max_details_per_cycle": 1})
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=detail_html)
    result = _scraper(cfg, http, env).run()
    assert http.detail_calls == 1
    assert any(a.metadata.get("detail_deferred") for a in result.new)
