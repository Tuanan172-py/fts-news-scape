"""
Tests BaodautuScraper — HTML listing + Bronze full raw HTML capture.

Nguồn HTML-listing đầu tiên của repo (RSS của baodautu hỏng vĩnh viễn ở server).
Fixtures thật: listing tải live, trang detail tái tạo TỪ BRONZE đã capture.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from _fakes import FakeHTTP
from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.scrapers import REGISTRY
from src.scrapers.baodautu import BaodautuScraper, _parse_detail_date

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def listing_html():
    return (FIXTURES / "baodautu_listing_d2.html").read_text(encoding="utf-8")


@pytest.fixture
def detail_html():
    return (FIXTURES / "baodautu_detail_page.html").read_text(encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    dedup = DedupCache(store, legacy_json_path="")
    yield dedup
    dedup.close()


def _config(**over):
    cfg = {
        "name": "baodautu", "enabled": True, "timeout": 30, "language": "vi",
        "base_url": "https://baodautu.vn",
        "listing": {
            "categories": [{"slug": "toan-canh-dau-tu", "id": 2,
                            "name": "Toàn cảnh đầu tư"}],
            "pages_per_cycle": 1,
            "item_selector": "article",
            "link_selector": "a[href]",
            "link_pattern": r"-d\d+\.html",
            "sapo_selector": "div.sapo_thumb_news, div.desc_list_news_home",
        },
        "detail": {"content_selector": "#content_detail_news",
                   "date_scope_selector": "span.post-time",
                   "author_selector": "a.author",
                   "max_details_per_cycle": 30},
        "watchlist": ["HPG", "FPT", "VNM"],
        "fuzzy_dedup": False,
    }
    cfg.update(over)
    return cfg


def _scraper(cfg, http, dedup):
    s = BaodautuScraper(cfg, http, dedup)
    s.backoff = None
    return s


def _http(listing_html, detail_html):
    # listing đi qua get() với URL chứa "-d2"; detail đi qua get_response()
    return FakeHTTP(listing_html=listing_html, detail_html=detail_html,
                    listing_match="-d2")


def test_registered():
    assert REGISTRY["baodautu"] is BaodautuScraper


def test_page_url_trailing_slash(env):
    """⚠️ Trang 1 PHẢI có / cuối; trang >1 PHẢI KHÔNG có / cuối (thêm vào → 404)."""
    s = _scraper(_config(), FakeHTTP(), env)
    assert s._page_url("toan-canh-dau-tu", 2, 1) == \
        "https://baodautu.vn/toan-canh-dau-tu-d2/"
    p2 = s._page_url("toan-canh-dau-tu", 2, 2)
    assert p2 == "https://baodautu.vn/toan-canh-dau-tu-d2/p2"
    assert not p2.endswith("/"), "thêm / cuối vào p<N> → 404"


def test_listing_parsed(env, listing_html, detail_html):
    s = _scraper(_config(), _http(listing_html, detail_html), env)
    items = s.fetch_list()
    assert len(items) >= 10
    for it in items:
        assert it["link"] and it["title"]
        assert it["_cat_name"] == "Toàn cảnh đầu tư"


def test_div_thumbblock_would_match_nothing(listing_html):
    """Bẫy: class `thumbblock` nằm trên thẻ <a> ẢNH, KHÔNG phải <div>.
    Kế hoạch gốc ghi item_selector='div.thumbblock' và sẽ khớp 0 node."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(listing_html, "lxml")
    assert "thumbblock" in listing_html            # chuỗi CÓ trong HTML
    assert soup.select("div.thumbblock") == []      # nhưng div.thumbblock = 0 node
    assert len(soup.select("article")) > 10         # item thật là <article>


def test_capture_happy_path(env, listing_html, detail_html):
    http = _http(listing_html, detail_html)
    result = _scraper(_config(), http, env).run()
    assert len(result.new) > 0
    a = [x for x in result.new
         if x.metadata["capture"]["capture_status"] == "ok"][0]
    assert a.source_domain == "baodautu.vn"
    assert a.url.startswith("https://baodautu.vn/")
    assert a.metadata["language"] == "vi"
    cap = a.metadata["capture"]
    assert Path(cap["html_path"]).read_text(encoding="utf-8") == detail_html
    assert len(a.content_text) > 0


def test_content_selector_avoids_js_template(env, listing_html, detail_html):
    """BẪY: source có chuỗi template JS `<div class="content">'+content+'</div>'`
    của widget bình luận. Selector `.content` sẽ bắt nhầm node đó.
    Chỉ #content_detail_news là đúng."""
    assert "'+content+'" in detail_html, "fixture phải giữ nguyên cái bẫy"
    http = _http(listing_html, detail_html)
    result = _scraper(_config(), http, env).run()
    a = [x for x in result.new
         if x.metadata["capture"]["capture_status"] == "ok"][0]
    assert "'+content+'" not in a.content_html
    assert "'+content+'" not in a.content_text
    assert len(a.content_text) > 200


def test_date_parsed_from_detail(env, listing_html, detail_html):
    """Listing KHÔNG có ngày → published_at phải được điền ở enrich() từ detail."""
    http = _http(listing_html, detail_html)
    result = _scraper(_config(), http, env).run()
    a = [x for x in result.new
         if x.metadata["capture"]["capture_status"] == "ok"][0]
    assert a.published_at == "2026-09-07T10:38:00+07:00"
    assert a.published_at.endswith("+07:00")


def test_author_parsed(env, listing_html, detail_html):
    http = _http(listing_html, detail_html)
    result = _scraper(_config(), http, env).run()
    a = [x for x in result.new
         if x.metadata["capture"]["capture_status"] == "ok"][0]
    assert a.author == "Phong Bình"


def test_missing_date_recorded_not_faked(env, listing_html, detail_html):
    """Không khớp ngày → published_at RỖNG + ghi missing. TUYỆT ĐỐI không bịa timestamp."""
    stripped = detail_html.replace("07/09/2026 10:38", "")
    http = _http(listing_html, stripped)
    result = _scraper(_config(), http, env).run()
    a = [x for x in result.new
         if x.metadata["capture"]["capture_status"] == "ok"][0]
    assert a.published_at == ""
    assert "published_at" in a.metadata["capture"]["missing"]


def test_parse_detail_date_unit():
    html = ('<html><body><main class="main_content">'
            '<span class="post-time"> - 07/09/2026 10:38</span>'
            '<div id="content_detail_news"><p>ngày 28/8/2026 trong thân bài</p></div>'
            '</main></body></html>')
    # scope hẹp → lấy đúng ngày đăng, không dính ngày trong thân bài
    assert _parse_detail_date(html, "span.post-time") == "2026-09-07T10:38:00+07:00"
    assert _parse_detail_date(html, "khong-ton-tai") == "2026-09-07T10:38:00+07:00"
    assert _parse_detail_date("", "span.post-time") == ""
    assert _parse_detail_date("<p>không có ngày</p>", "span.post-time") == ""
    # ngày không hợp lệ → rỗng, không raise
    bad = '<span class="post-time">32/13/2026 99:99</span>'
    assert _parse_detail_date(bad, "span.post-time") == ""


def test_detail_failure_keeps_summary(env, listing_html):
    http = FakeHTTP(listing_html=listing_html, detail_html=None, listing_match="-d2")
    result = _scraper(_config(), http, env).run()
    assert len(result.new) > 0
    for a in result.new:
        assert a.metadata["capture"]["capture_status"] == "failed"
        assert a.content_text == a.summary
    assert any("detail fetch failed" in e for e in result.errors)


def test_listing_failure_isolated(env, listing_html, detail_html):
    """1 chuyên mục chết → error, chuyên mục khác vẫn parse."""
    class PartialHTTP(FakeHTTP):
        def get(self, url, **kw):
            if "-d999" in url:
                return None
            return super().get(url, **kw)

    cfg = _config(listing={
        "categories": [{"slug": "chet", "id": 999, "name": "Chết"},
                       {"slug": "toan-canh-dau-tu", "id": 2, "name": "Toàn cảnh đầu tư"}],
        "pages_per_cycle": 1,
        "item_selector": "article",
        "link_selector": "a[href]",
        "link_pattern": r"-d\d+\.html",
        "sapo_selector": "div.sapo_thumb_news, div.desc_list_news_home",
    })
    http = PartialHTTP(listing_html=listing_html, detail_html=detail_html,
                       listing_match="-d2")
    result = _scraper(cfg, http, env).run()
    assert any("listing fetch failed" in e for e in result.errors)
    assert len(result.new) > 0


def test_listing_zero_items_flags_drift(env, detail_html):
    """Template đổi → 0 item → phải ghi error rõ ràng, KHÔNG im lặng."""
    http = FakeHTTP(listing_html="<html><body>nothing</body></html>",
                    detail_html=detail_html, listing_match="-d2")
    result = _scraper(_config(), http, env).run()
    assert result.new == []
    assert any("template drift" in e for e in result.errors)


def test_max_details_cap(env, listing_html, detail_html):
    cfg = _config(detail={"content_selector": "#content_detail_news",
                          "date_scope_selector": "span.post-time",
                          "max_details_per_cycle": 1})
    http = _http(listing_html, detail_html)
    result = _scraper(cfg, http, env).run()
    assert http.detail_calls == 1
    assert any(a.metadata.get("detail_deferred") for a in result.new)


def test_config_file_sane():
    import yaml
    p = Path(__file__).resolve().parent.parent / "config" / "domains" / "baodautu.yaml"
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert cfg["enabled"] is True
    assert cfg["method"] == "baodautu"
    assert "rss" not in cfg, "block rss: phải bị xoá hẳn — feed hỏng vĩnh viễn"
    assert cfg["detail"]["content_selector"] == "#content_detail_news"
    assert cfg["detail"]["date_scope_selector"] == "span.post-time"
    # class thumbblock nằm trên thẻ <a> ảnh, KHÔNG phải div → div.thumbblock khớp 0 node
    assert cfg["listing"]["item_selector"] == "article"
    assert len(cfg["listing"]["categories"]) == 6
    ids = {c["id"] for c in cfg["listing"]["categories"]}
    assert 80 not in ids, "d80 'Quảng bá' là PR — không được đưa vào"
    # slug d5 có HAI dấu gạch ngang — dễ bị 'sửa' nhầm
    d5 = [c for c in cfg["listing"]["categories"] if c["id"] == 5][0]
    assert d5["slug"] == "ngan-hang--bao-hiem"
