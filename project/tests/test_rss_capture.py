"""
Tests RssCaptureScraper — RSS list + Bronze full raw HTML capture (method: rss_capture).

Fixtures thật (vietnambiz, captured live 2026-09-07). Không chạm mạng.
Bao phủ: registry, capture happy path (byte-exact), selector hit, fallback
content:encoded khi capture fail, cap max_details, feed chết bị cô lập,
và filter kế thừa từ RSSScraper.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from _fakes import FakeHTTP
from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.scrapers import REGISTRY
from src.scrapers.rss_capture import RssCaptureScraper

FIXTURES = Path(__file__).parent / "fixtures"
FEED_URL = "https://vietnambiz.vn/chung-khoan.rss"


@pytest.fixture
def feed_bytes():
    return (FIXTURES / "vietnambiz_capture_feed.xml").read_bytes()


@pytest.fixture
def detail_html():
    return (FIXTURES / "vietnambiz_detail_page.html").read_text(encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # cô lập RawStore ghi data/raw_html vào tmp
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    dedup = DedupCache(store, legacy_json_path="")
    yield dedup
    dedup.close()


def _config(**over):
    cfg = {
        "name": "vietnambiz", "enabled": True, "timeout": 30, "language": "vi",
        "base_url": "https://vietnambiz.vn/",
        "rss": {"feeds": [{"url": FEED_URL, "name": "VietnamBiz Chứng khoán"}]},
        "detail": {"content_selector": "div.vnbcbc-body",
                   "max_details_per_cycle": 30},
        "watchlist": ["VIX", "FPT", "VNM"],
        "fuzzy_dedup": False,   # fixture có 3 bài khác hẳn nhau; tắt cho tiền định
    }
    cfg.update(over)
    return cfg


def _scraper(cfg, http, dedup):
    s = RssCaptureScraper(cfg, http, dedup)
    s.backoff = None  # tắt sleep của SourceBackoff trong unit test
    return s


# -- registry ---------------------------------------------------------------

def test_registered():
    assert "_rss_capture" in REGISTRY
    assert REGISTRY["_rss_capture"] is RssCaptureScraper


def test_inherits_rss_scraper():
    """Kế thừa RSSScraper → fetch_list/parse_item/filter dùng chung, không copy."""
    from src.scrapers.rss_generic import RSSScraper
    assert issubclass(RssCaptureScraper, RSSScraper)
    # không tự định nghĩa lại 2 hook này
    assert "fetch_list" not in RssCaptureScraper.__dict__
    assert "parse_item" not in RssCaptureScraper.__dict__


# -- Bronze capture ---------------------------------------------------------

def test_capture_happy_path(env, feed_bytes, detail_html):
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=detail_html)
    result = _scraper(_config(), http, env).run()

    assert len(result.new) > 0
    captured = [a for a in result.new
                if a.metadata.get("capture", {}).get("capture_status") == "ok"]
    assert captured, "ít nhất 1 bài capture ok"
    a = captured[0]
    assert a.source_domain == "vietnambiz.vn"
    assert a.published_at.endswith("+07:00")     # pubDate 'GMT+7' → _parse_raw_date
    assert a.metadata["language"] == "vi"
    # AC2/AC7 — artifact byte-exact, raw không bị mutate
    cap = a.metadata["capture"]
    assert Path(cap["html_path"]).read_text(encoding="utf-8") == detail_html
    assert cap["http_status"] == 200
    assert len(a.content_html) > 0
    assert len(a.content_text) > 0
    # image manifest read-only
    assert any("cdn.vietnambiz.vn" in (i["resolved_url"] or "") for i in cap["images"])
    # _inline_html không được rò vào metadata lưu DB
    assert "_inline_html" not in a.metadata


def test_content_selector_hits(env, feed_bytes, detail_html):
    """div.vnbcbc-body phải khớp thật — nếu miss thì capture_status=partial
    → SELECTOR_BROKEN → agent hold bài (audit 01 §A2)."""
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=detail_html)
    result = _scraper(_config(), http, env).run()
    for a in result.new:
        cap = a.metadata["capture"]
        assert "main_content_node" not in cap.get("missing", [])
        assert "incomplete_render" not in cap.get("missing", [])
        assert cap["capture_status"] == "ok"


def test_default_article_selector_would_break(env, feed_bytes, detail_html):
    """Regression cho audit 01 §A2: trang vietnambiz KHÔNG có thẻ <article>,
    nên default 'article' làm mọi bài thành partial. Selector là BẮT BUỘC."""
    cfg = _config(detail={"max_details_per_cycle": 30})   # không có content_selector
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=detail_html)
    result = _scraper(cfg, http, env).run()
    assert result.new
    for a in result.new:
        assert a.metadata["capture"]["capture_status"] == "partial"
        assert "incomplete_render" in a.metadata["capture"]["missing"]


def test_detail_failure_keeps_summary(env, feed_bytes):
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=None)  # get_response → None
    result = _scraper(_config(), http, env).run()
    assert len(result.new) > 0
    for a in result.new:
        assert a.metadata["capture"]["capture_status"] == "failed"
        assert a.content_text == a.summary
    assert any("detail fetch failed" in e for e in result.errors)


def test_inline_content_fallback_on_failure(env, detail_html):
    """content:encoded chỉ là body DỰ PHÒNG khi capture fail — không bao giờ là Bronze."""
    body = "<p>" + ("Nội dung đầy đủ trong feed. " * 40) + "</p>"
    feed = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">'
        "<channel><title>t</title>"
        "<item><title>Bài có content encoded</title>"
        "<link>https://vietnambiz.vn/bai-co-inline-123.htm</link>"
        "<description>Tóm tắt ngắn</description>"
        "<pubDate>Mon, 07 Sep 2026 19:41:53 GMT+7</pubDate>"
        f"<content:encoded><![CDATA[{body}]]></content:encoded>"
        "</item></channel></rss>"
    ).encode("utf-8")

    http = FakeHTTP(feed_bytes=feed, detail_html=None)   # capture thất bại
    result = _scraper(_config(), http, env).run()
    assert len(result.new) == 1
    a = result.new[0]
    assert a.metadata["capture"]["capture_status"] == "failed"   # vẫn KHÔNG phải Bronze
    assert "Nội dung đầy đủ trong feed" in a.content_html        # dùng inline làm body
    assert len(a.content_text) > len(a.summary)


def test_max_details_cap(env, feed_bytes, detail_html):
    cfg = _config(detail={"content_selector": "div.vnbcbc-body",
                          "max_details_per_cycle": 1})
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=detail_html)
    result = _scraper(cfg, http, env).run()
    assert http.detail_calls == 1
    deferred = [a for a in result.new if a.metadata.get("detail_deferred")]
    assert deferred, "bài vượt cap phải được đánh dấu detail_deferred"


def test_dead_feed_isolated(env, feed_bytes, detail_html):
    """1 feed chết → error, feed còn lại vẫn parse (feed-level isolation)."""
    class PartialHTTP(FakeHTTP):
        def get_bytes(self, url, **kw):
            return None if "dead" in url else self.feed_bytes

    cfg = _config(rss={"feeds": [
        {"url": "https://vietnambiz.vn/dead.rss", "name": "Dead"},
        {"url": FEED_URL, "name": "VietnamBiz Chứng khoán"},
    ]})
    http = PartialHTTP(feed_bytes=feed_bytes, detail_html=detail_html)
    result = _scraper(cfg, http, env).run()
    assert any("feed fetch failed" in e for e in result.errors)
    assert len(result.new) > 0, "feed sống vẫn phải cho ra bài"


def test_filter_inherited(env, feed_bytes, detail_html):
    """filter.any/none kế thừa từ RSSScraper (audit 01 §A1) — 0 dòng code thêm."""
    cfg = _config(filter={"any": ["khong-bao-gio-khop-xyz"], "drop_unmatched": True})
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=detail_html)
    result = _scraper(cfg, http, env).run()
    assert result.new == []


def test_category_meta_optional(env, feed_bytes, detail_html):
    """category_meta không cấu hình → không đụng gì tới categories (mặc định tắt)."""
    http = FakeHTTP(feed_bytes=feed_bytes, detail_html=detail_html)
    result = _scraper(_config(), http, env).run()
    a = [x for x in result.new
         if x.metadata["capture"]["capture_status"] == "ok"][0]
    assert a.categories == ["VietnamBiz Chứng khoán"]   # chỉ tên feed


def test_meta_content_helper():
    from src.scrapers.rss_capture import _meta_content
    html = ('<html><head>'
            '<meta property="article:section" content="Chính sách tài chính">'
            '<meta name="category_url" content="https://x/y">'
            '</head><body></body></html>')
    assert _meta_content(html, "article:section") == "Chính sách tài chính"
    assert _meta_content(html, "category_url") == "https://x/y"   # fallback name=
    assert _meta_content(html, "khong-ton-tai") == ""
    assert _meta_content("", "article:section") == ""
    assert _meta_content(html, "") == ""
