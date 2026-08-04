"""
Tests cho FireAntScraper — mock HTTP (không token thật), fixture từ
thamkhao/docs_fireant field names.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.scrapers.fireant import FireAntScraper

LIST_POST = {
    "post_id": 38267319,
    "title": "Vingroup tính xây tổ hợp giải trí VinWonders tại Ấn Độ",
    "description": "Ngày 04/02/2026 tại Chennai, Tập đoàn Vingroup công bố...",
    "content": "",
    "type": 1,
    "date": "2026-02-04T17:50:00+07:00",
    "taggedSymbols": [{"symbol": "VIC"}],
    "post_source": {"name": "An ninh tiền tệ", "url": "https://antt.vn/"},
}

DETAIL_POST = {
    **LIST_POST,
    "content": "<p>Ngày 04/02/2026 tại Chennai, Tập đoàn Vingroup công bố kế hoạch "
               "xây dựng tổ hợp giải trí VinWonders và khách sạn Vinpearl. Dự án có "
               "quy mô lớn với tổng vốn đầu tư hàng trăm triệu USD.</p>",
}


class FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeHTTP:
    def __init__(self, list_status=200, list_payload=None,
                 detail_status=200, detail_payload=None):
        self.list_status = list_status
        self.list_payload = list_payload
        self.detail_status = detail_status
        self.detail_payload = detail_payload
        self.list_calls = 0

    def get_response(self, url, **kw):
        # detail = /posts/{id} (số nhiều + id); list = /posts (+ query params)
        if re.search(r"/posts/\d+", url):
            return FakeResp(self.detail_status, self.detail_payload)
        self.list_calls += 1
        return FakeResp(self.list_status, self.list_payload)


@pytest.fixture
def dedup(tmp_path):
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    d = DedupCache(store, legacy_json_path="")
    yield d
    d.close()


def _config(token="real-token-abc", watchlist=None):
    return {
        "name": "fireant", "enabled": True, "timeout": 30,
        "api": {"params": {"type": 1, "offset": 0, "limit": 20}},
        "detail": {"max_details_per_cycle": 30},
        "watchlist": watchlist or ["VIC"],
        "_secrets": {"fireant_token": token},
    }


def test_happy_path_two_step(dedup):
    http = FakeHTTP(list_payload=[LIST_POST], detail_payload=DETAIL_POST)
    scraper = FireAntScraper(_config(), http, dedup)
    result = scraper.run()
    assert len(result.new) == 1
    a = result.new[0]
    assert a.url == "https://fireant.vn/bai-viet/38267319"
    assert a.symbols == ["VIC"]
    assert a.published_at == "2026-02-04T17:50:00+07:00"
    assert "VinWonders" in a.content_html      # detail content merged
    assert len(a.content_text) > 50
    assert a.metadata["source_name"] == "An ninh tiền tệ"


def test_missing_token_disables_scraper(dedup):
    http = FakeHTTP(list_payload=[LIST_POST])
    scraper = FireAntScraper(_config(token=""), http, dedup)
    result = scraper.run()
    assert result.fetched == 0 and result.new == []
    assert http.list_calls == 0  # không gọi API khi không có token


def test_placeholder_token_disables(dedup):
    scraper = FireAntScraper(_config(token="PASTE_BEARER_TOKEN_HERE"),
                             FakeHTTP(), dedup)
    assert scraper.disabled


def test_token_with_bearer_prefix_stripped(dedup):
    # user dán nguyên "Bearer eyJ..." → không được nhân đôi thành "Bearer Bearer"
    scraper = FireAntScraper(_config(token="Bearer eyJabc123"), FakeHTTP(), dedup)
    assert scraper.auth_headers["Authorization"] == "Bearer eyJabc123"
    assert not scraper.disabled


def test_401_self_disable_no_retry_storm(dedup):
    http = FakeHTTP(list_status=401)
    scraper = FireAntScraper(_config(watchlist=["VIC", "HPG", "VNM"]), http, dedup)
    result = scraper.run()
    # 401 ở symbol đầu → disable ngay, KHÔNG gọi tiếp 2 symbol còn lại
    assert http.list_calls == 1
    assert scraper.disabled
    assert any("token expired" in e for e in result.errors)


def test_detail_401_keeps_article_with_summary(dedup):
    http = FakeHTTP(list_payload=[LIST_POST], detail_status=401)
    scraper = FireAntScraper(_config(), http, dedup)
    result = scraper.run()
    assert len(result.new) == 1
    assert result.new[0].content_text == result.new[0].summary
    assert scraper.disabled
