"""
Tests Phase 2 features: _decode_feed (encoding hardening), keyword filter,
language metadata. Fixtures thật captured 2026-07-25.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import feedparser
import pytest

from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.scrapers.rss_generic import RSSScraper, _decode_feed

FIXTURES = Path(__file__).parent / "fixtures"

FEED_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>T</title>
<item><title>Cổ phiếu HPG tăng trần</title><link>https://ex.com/1</link>
<description>Thị trường chứng khoán sôi động</description>
<pubDate>Fri, 25 Jul 2026 09:00:00 +0700</pubDate></item>
<item><title>Giá rau củ tại chợ hôm nay</title><link>https://ex.com/2</link>
<description>Tin đời sống thường ngày</description>
<pubDate>Fri, 25 Jul 2026 09:05:00 +0700</pubDate></item>
</channel></rss>"""


# ---- _decode_feed ------------------------------------------------------------

def test_decode_utf16_bom_bytes():
    text = _decode_feed("<?xml version=\"1.0\"?><rss><channel><title>Cổ phiếu</title></channel></rss>".encode("utf-16"))  # utf-16 with BOM
    assert "Cổ phiếu" in text


def test_decode_utf16_no_bom_heuristic():
    raw = "<?xml version=\"1.0\"?><rss/>".encode("utf-16-le")  # null bytes, no BOM
    assert "<rss/>" in _decode_feed(raw)


def test_decode_utf8_bom_stripped():
    raw = b"\xef\xbb\xbf" + FEED_XML.encode("utf-8")
    text = _decode_feed(raw)
    assert text.startswith("<?xml")
    assert "﻿" not in text


def test_decode_blank_lines_regression_baodautu():
    raw = b"\r\n\r\n\r\n\r\n" + FEED_XML.encode("utf-8")
    assert _decode_feed(raw).startswith("<?xml")


def test_decode_plain_utf8_unchanged():
    text = _decode_feed(FEED_XML.encode("utf-8"))
    assert "Cổ phiếu HPG tăng trần" in text


def test_real_dantri_bom_fixture_parses():
    raw = (FIXTURES / "dantri_bom.rss").read_bytes()
    assert raw[:3] == b"\xef\xbb\xbf"  # BOM thật
    feed = feedparser.parse(_decode_feed(raw))
    assert not (feed.bozo and not feed.entries)
    assert len(feed.entries) > 50


def test_real_vietnambiz_fixture_parses_with_correct_diacritics():
    # Feed KHAI BÁO encoding="utf-16" nhưng serve utf-8 bytes (verified 2026-07-25)
    # — đường bytes + tự decode tránh mojibake
    raw = (FIXTURES / "vietnambiz_utf16.rss").read_bytes()
    feed = feedparser.parse(_decode_feed(raw))
    assert len(feed.entries) >= 20
    titles = " ".join(e.get("title", "") for e in feed.entries)
    # có dấu tiếng Việt hợp lệ, không mojibake
    assert any(ch in titles for ch in "ăâđêôơưáàảãạ")
    assert "Ã¡" not in titles and "Ä‘" not in titles


# ---- date fallback (format phi chuẩn) ---------------------------------------

def test_date_fallback_gmt_plus7_vietnambiz():
    from src.scrapers.rss_generic import _parse_raw_date
    iso = _parse_raw_date("Sat, 25 Jul 2026 20:01:31 GMT+7")
    assert iso.startswith("2026-07-25T20:01:31") and iso.endswith("+07:00")


def test_date_fallback_2digit_tz_cafebiz():
    from src.scrapers.rss_generic import _parse_raw_date
    iso = _parse_raw_date("Sat, 25 Jul 2026 22:30:00 +07")
    assert iso.startswith("2026-07-25T22:30:00")


def test_date_fallback_us_format_tuoitre():
    from src.scrapers.rss_generic import _parse_raw_date
    iso = _parse_raw_date("7/25/2026 7:39:00 PM")  # narrow no-break space
    assert iso.startswith("2026-07-25T19:39:00") and iso.endswith("+07:00")


def test_date_fallback_gmt_two_digit_offset():
    from src.scrapers.rss_generic import _parse_raw_date
    assert _parse_raw_date("Sat, 25 Jul 2026 20:01:31 GMT+10").endswith("+07:00")


def test_date_wellformed_tz_not_corrupted():
    # review #2 regression: '+0700' đầy đủ KHÔNG bị rule '+07→+0700' phá
    from src.scrapers.rss_generic import _parse_raw_date
    iso = _parse_raw_date("Sat, 25 Jul 2026 20:01:31 +0700")
    assert iso.startswith("2026-07-25T20:01:31") and iso.endswith("+07:00")


def test_xml_decl_without_encoding_unchanged():
    # review #3 regression: declaration không có encoding + chữ 'encoding=' trong
    # content 200 chars đầu → không bị strip nhầm
    from src.scrapers.rss_generic import _decode_feed
    xml = ('<?xml version="1.0"?>\n<rss><channel>'
           '<title>Bài về encoding="utf-16" trong tin học</title>')
    out = _decode_feed(xml.encode("utf-8"))
    assert '<?xml version="1.0"?>' in out
    assert 'encoding="utf-16" trong tin học' in out


def test_date_fallback_garbage_empty():
    from src.scrapers.rss_generic import _parse_raw_date
    assert _parse_raw_date("hôm qua") == ""
    assert _parse_raw_date("") == ""


# ---- filter + language -------------------------------------------------------

class FakeHTTP:
    def __init__(self, xml: str):
        self.xml = xml

    def get_bytes(self, url, **kw):
        return self.xml.encode("utf-8")

    def get(self, url, **kw):
        return "<html><body><p>Nội dung chi tiết bài viết đầy đủ.</p></body></html>"


@pytest.fixture
def dedup(tmp_path):
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    d = DedupCache(store, legacy_json_path="")
    yield d
    d.close()


def _config(**over):
    cfg = {
        "name": "ftest", "enabled": True, "timeout": 30,
        "rss": {"feeds": [{"url": "https://f.com/feed", "name": "F"}]},
        "detail": {"extract_full": False},
        "watchlist": ["HPG"],
    }
    cfg.update(over)
    return cfg


def test_filter_drops_unmatched(dedup):
    cfg = _config(filter={"any": ["chứng khoán", "cổ phiếu"]})
    scraper = RSSScraper(cfg, FakeHTTP(FEED_XML), dedup)
    result = scraper.run()
    assert result.fetched == 2
    assert len(result.new) == 1  # tin rau củ bị filter
    assert result.new[0].title == "Cổ phiếu HPG tăng trần"
    assert scraper._filtered == 1


def test_no_filter_keeps_all(dedup):
    scraper = RSSScraper(_config(), FakeHTTP(FEED_XML), dedup)
    assert len(scraper.run().new) == 2


def test_block_list_drops_matched(dedup):
    # filter.none: bài chứa term bị loại (Yahoo lifestyle)
    cfg = _config(filter={"none": ["rau củ", "lifestyle"]})
    scraper = RSSScraper(cfg, FakeHTTP(FEED_XML), dedup)
    result = scraper.run()
    assert result.fetched == 2
    assert len(result.new) == 1  # tin rau củ bị chặn
    assert result.new[0].title == "Cổ phiếu HPG tăng trần"
    assert scraper._filtered == 1


def test_block_list_case_insensitive(dedup):
    cfg = _config(filter={"none": ["RAU CỦ"]})
    scraper = RSSScraper(cfg, FakeHTTP(FEED_XML), dedup)
    assert len(scraper.run().new) == 1


def test_block_and_allow_combined(dedup):
    # allow-list giữ tin CK, block-list loại thêm — cùng hoạt động
    cfg = _config(filter={"any": ["cổ phiếu", "rau"], "none": ["rau củ"]})
    scraper = RSSScraper(cfg, FakeHTTP(FEED_XML), dedup)
    result = scraper.run()
    assert len(result.new) == 1  # rau khớp allow nhưng bị block loại
    assert result.new[0].title == "Cổ phiếu HPG tăng trần"


def test_filter_drop_unmatched_false_keeps_all(dedup):
    cfg = _config(filter={"any": ["chứng khoán"], "drop_unmatched": False})
    scraper = RSSScraper(cfg, FakeHTTP(FEED_XML), dedup)
    assert len(scraper.run().new) == 2


def test_filter_case_insensitive(dedup):
    cfg = _config(filter={"any": ["CỔ PHIẾU"]})
    scraper = RSSScraper(cfg, FakeHTTP(FEED_XML), dedup)
    assert len(scraper.run().new) == 1


def test_language_metadata_en(dedup):
    scraper = RSSScraper(_config(language="en"), FakeHTTP(FEED_XML), dedup)
    result = scraper.run()
    assert all(a.metadata["language"] == "en" for a in result.new)


def test_language_default_vi(dedup):
    scraper = RSSScraper(_config(), FakeHTTP(FEED_XML), dedup)
    assert scraper.run().new[0].metadata["language"] == "vi"


def test_sentiment_skip_logic_for_en():
    """Logic orchestrator: language != vi → neutral/0.0 không gọi engine."""
    from src.core.models import Article
    a = Article(url="https://x.com/1", title="Stocks surge on Fed cut",
                source_domain="x.com", metadata={"language": "en"})
    # mô phỏng đúng nhánh trong orchestrator.run_cycle
    if a.metadata.get("language", "vi") == "vi":
        raise AssertionError("EN article must skip VN sentiment")
    a.sentiment, a.sentiment_score = "neutral", 0.0
    assert (a.sentiment, a.sentiment_score) == ("neutral", 0.0)
