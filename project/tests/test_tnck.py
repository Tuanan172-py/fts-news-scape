"""
Tests cho TnckScraper — fixture thật (captured 2026-07-24), mock HTTP.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.scrapers.tnck import TnckScraper

FIXTURES = Path(__file__).parent / "fixtures"

DETAIL_HTML = """<html><head><title>Bài</title></head><body><article>
<h1>Tiêu đề</h1><p>Đoạn nội dung chính của bài viết dài đủ để trafilatura nhận diện.
Thị trường chứng khoán hôm nay có nhiều biến động đáng chú ý với thanh khoản cao.</p>
</article></body></html>"""


class FakeHTTP:
    def __init__(self, zone_json, detail_html=DETAIL_HTML):
        self.zone_json = zone_json
        self.detail_html = detail_html

    def get_json(self, url, **kw):
        return self.zone_json

    def get(self, url, **kw):
        return self.detail_html


@pytest.fixture
def fixture_zone():
    return json.loads((FIXTURES / "tnck_zone_response.json").read_text(encoding="utf-8"))


@pytest.fixture
def dedup(tmp_path):
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    d = DedupCache(store, legacy_json_path="")
    yield d
    d.close()


def _config(**over):
    cfg = {
        "name": "tnck", "enabled": True, "timeout": 30,
        "api": {"zones": [4], "pages_per_cycle": 1},
        "detail": {"max_details_per_cycle": 50},
        "watchlist": ["HPG", "PLX", "EIB", "PVP"],
    }
    cfg.update(over)
    return cfg


def test_happy_path_real_fixture(dedup, fixture_zone):
    scraper = TnckScraper(_config(), FakeHTTP(fixture_zone), dedup)
    result = scraper.run()
    assert result.fetched == 40
    assert len(result.new) == 40
    for a in result.new:
        assert a.url.startswith("https://www.tinnhanhchungkhoan.vn/")
        assert a.title
        assert a.source_domain == "tinnhanhchungkhoan.vn"
    # epoch date parse → ISO +07:00
    dated = [a for a in result.new if a.published_at]
    assert len(dated) == 40
    assert all(a.published_at.endswith("+07:00") for a in dated)
    # ticker tagging client-side hoạt động (PLX có trong fixture title đầu)
    assert any("PLX" in a.symbols for a in result.new)
    # zone name → category
    assert result.new[0].categories == ["Thông tin doanh nghiệp"]


def test_empty_contents_no_crash(dedup):
    scraper = TnckScraper(_config(), FakeHTTP({"data": {"contents": []}}), dedup)
    result = scraper.run()
    assert result.fetched == 0 and result.new == []
    assert result.errors == []


def test_fetch_failure_recorded(dedup):
    scraper = TnckScraper(_config(), FakeHTTP(None), dedup)
    result = scraper.run()
    assert result.new == []
    assert any("fetch failed" in e for e in result.errors)


def test_bad_epoch_date_no_crash(dedup, fixture_zone):
    fixture_zone["data"]["contents"][0]["date"] = "not-a-number"
    scraper = TnckScraper(_config(), FakeHTTP(fixture_zone), dedup)
    result = scraper.run()
    assert len(result.new) == 40  # item vẫn giữ, published_at rỗng
    bad = [a for a in result.new if not a.published_at]
    assert len(bad) == 1


def test_dedup_second_run(dedup, fixture_zone):
    http = FakeHTTP(fixture_zone)
    scraper = TnckScraper(_config(), http, dedup)
    assert len(scraper.run().new) == 40
    assert len(scraper.run().new) == 0
