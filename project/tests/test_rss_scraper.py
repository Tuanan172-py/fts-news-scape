"""
Tests cho RSSScraper generic — fixture thật (Vietstock, VnEconomy, captured
2026-07-24) + edge cases synthetic.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.scrapers.rss_generic import RSSScraper

FIXTURES = Path(__file__).parent / "fixtures"

DETAIL_HTML = """<html><body><article><h1>Bài viết</h1>
<p>Nội dung chính đầy đủ của bài viết về thị trường chứng khoán Việt Nam hôm nay,
với nhiều thông tin quan trọng cho nhà đầu tư theo dõi diễn biến giao dịch.</p>
</article></body></html>"""

BAD_XML = "this is not xml at all <<<>>>"

ENTRY_NO_LINK_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>T</title>
<item><title>Bài không có link</title><description>x</description></item>
<item><title>Bài đủ</title><link>https://ex.com/ok</link>
<description>mô tả</description>
<pubDate>Fri, 24 Jul 2026 14:00:00 +0700</pubDate></item>
</channel></rss>"""


class FakeHTTP:
    def __init__(self, feed_map: dict, detail_html=DETAIL_HTML):
        self.feed_map = feed_map
        self.detail_html = detail_html

    def get_bytes(self, url, **kw):
        """Feed fetch path (RSSScraper dùng bytes + _decode_feed)."""
        val = self.feed_map.get(url)
        if val is None:
            return None
        return val.encode("utf-8") if isinstance(val, str) else val

    def get(self, url, **kw):
        if url in self.feed_map:
            return self.feed_map[url]
        return self.detail_html


@pytest.fixture
def dedup(tmp_path):
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    d = DedupCache(store, legacy_json_path="")
    yield d
    d.close()


def _config(feeds, **over):
    cfg = {
        "name": "rsstest", "enabled": True, "timeout": 30,
        "rss": {"feeds": feeds},
        "detail": {"extract_full": True, "max_details_per_cycle": 100},
        "watchlist": ["HPG", "FPT", "SSI"],
    }
    cfg.update(over)
    return cfg


def test_vietstock_feed_real_fixture(dedup):
    xml = (FIXTURES / "vietstock_feed.xml").read_text(encoding="utf-8")
    http = FakeHTTP({"https://vietstock.vn/feed": xml})
    scraper = RSSScraper(
        _config([{"url": "https://vietstock.vn/feed", "name": "VS CK"}]),
        http, dedup)
    result = scraper.run()
    assert result.fetched > 5
    assert len(result.new) == result.fetched
    for a in result.new:
        assert a.source_domain == "vietstock.vn"
        assert a.title and a.url.startswith("http")
        assert a.published_at.endswith("+07:00")  # pubDate +0700 → VN tz
        assert a.categories == ["VS CK"]
        assert len(a.content_text) > 50  # detail fetch


def test_vneconomy_feed_real_fixture(dedup):
    # VnEconomy: content:encoded chỉ khai báo namespace, item KHÔNG có
    # (verified 2026-07-24) → đi đường detail-fetch bình thường
    xml = (FIXTURES / "vneconomy_feed.xml").read_text(encoding="utf-8")
    http = FakeHTTP({"https://vneconomy.vn/feed": xml})
    scraper = RSSScraper(
        _config([{"url": "https://vneconomy.vn/feed", "name": "VnEco CK"}]),
        http, dedup)
    result = scraper.run()
    assert len(result.new) > 5
    for a in result.new:
        assert a.source_domain == "vneconomy.vn"
        assert len(a.content_text) > 50


INLINE_CONTENT_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel><title>T</title>
<item><title>Bài có content encoded</title><link>https://ex.com/inline</link>
<description>ngắn</description>
<content:encoded><![CDATA[<p>""" + ("Nội dung đầy đủ trong feed. " * 30) + """</p>]]></content:encoded>
<pubDate>Fri, 24 Jul 2026 14:00:00 +0700</pubDate></item>
</channel></rss>"""


def test_inline_content_skips_detail_fetch(dedup):
    class CountingHTTP(FakeHTTP):
        def __init__(self, feed_map):
            super().__init__(feed_map)
            self.detail_calls = 0

        def get(self, url, **kw):
            if url not in self.feed_map:
                self.detail_calls += 1
            return super().get(url, **kw)

    http = CountingHTTP({"https://f.com/feed": INLINE_CONTENT_XML})
    scraper = RSSScraper(
        _config([{"url": "https://f.com/feed", "name": "F"}]), http, dedup)
    result = scraper.run()
    assert len(result.new) == 1
    a = result.new[0]
    assert http.detail_calls == 0             # không fetch detail
    assert len(a.content_html) > 500          # dùng content:encoded
    assert "Nội dung đầy đủ" in a.content_text


def test_dead_feed_isolation(dedup):
    xml = (FIXTURES / "vietstock_feed.xml").read_text(encoding="utf-8")
    http = FakeHTTP({"https://ok.com/feed": xml, "https://dead.com/feed": None})
    scraper = RSSScraper(
        _config([{"url": "https://dead.com/feed", "name": "Dead"},
                 {"url": "https://ok.com/feed", "name": "OK"}]),
        http, dedup)
    result = scraper.run()
    assert any("Dead" in e for e in result.errors)
    assert result.fetched > 0  # feed sống vẫn chạy


def test_malformed_xml_no_crash(dedup):
    http = FakeHTTP({"https://bad.com/feed": BAD_XML})
    scraper = RSSScraper(
        _config([{"url": "https://bad.com/feed", "name": "Bad"}]), http, dedup)
    result = scraper.run()
    assert result.new == []
    assert any("parse failed" in e for e in result.errors)


def test_entry_without_link_skipped(dedup):
    http = FakeHTTP({"https://f.com/feed": ENTRY_NO_LINK_XML})
    scraper = RSSScraper(
        _config([{"url": "https://f.com/feed", "name": "F"}]), http, dedup)
    result = scraper.run()
    assert result.fetched == 2
    assert len(result.new) == 1  # entry thiếu link bị bỏ
    assert result.new[0].url == "https://ex.com/ok"


def test_leading_whitespace_before_xml_decl(dedup):
    # baodautu.vn trả \r\n×4 trước <?xml → phải lstrip (verified 2026-07-24)
    xml = "\r\n\r\n\r\n\r\n" + ENTRY_NO_LINK_XML
    http = FakeHTTP({"https://f.com/feed": xml})
    scraper = RSSScraper(
        _config([{"url": "https://f.com/feed", "name": "F"}]), http, dedup)
    result = scraper.run()
    assert result.fetched == 2  # parse thành công dù có leading whitespace


def test_extract_full_false_uses_summary(dedup):
    http = FakeHTTP({"https://f.com/feed": ENTRY_NO_LINK_XML})
    cfg = _config([{"url": "https://f.com/feed", "name": "F"}])
    cfg["detail"]["extract_full"] = False
    scraper = RSSScraper(cfg, http, dedup)
    result = scraper.run()
    assert result.new[0].content_text == result.new[0].summary
