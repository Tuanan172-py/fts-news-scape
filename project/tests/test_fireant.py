"""
Tests cho FireAntScraper — mock HTTP (không token thật) + Bronze capture JSON.

⚠️ Bronze của fireant là **JSON**, không phải HTML: trang web là Next.js SPA nên body
bài chỉ có trong response API. Test khẳng định response detail được lưu byte-exact và
SilverBuilder bóc được trường `content` ra khỏi JSON mà không nuốt key JSON.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.pipeline.silver_builder import SilverBuilder
from src.scrapers.fireant import FireAntScraper

LIST_POST = {
    "postID": 38267319,                       # API thật dùng camelCase
    "title": "Vingroup tính xây tổ hợp giải trí VinWonders tại Ấn Độ",
    "description": "Ngày 04/02/2026 tại Chennai, Tập đoàn Vingroup công bố...",
    "content": "",                            # list LUÔN rỗng → phải gọi detail
    "type": 1,
    "date": "2026-02-04T17:50:00+07:00",
    "taggedSymbols": [{"symbol": "VIC"}],
    "postSource": {"name": "An ninh tiền tệ", "url": "https://antt.vn/"},
}

DETAIL_POST = {
    **LIST_POST,
    "content": "<p>Ngày 04/02/2026 tại Chennai, Tập đoàn Vingroup công bố kế hoạch "
               "xây dựng tổ hợp giải trí VinWonders và khách sạn Vinpearl. Dự án có "
               "quy mô lớn với tổng vốn đầu tư hàng trăm triệu USD.</p>",
}


class FakeResp:
    """Mô phỏng requests.Response đủ cho RawStore (content/headers/encoding)."""

    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.ok = 200 <= status_code < 300
        body = json.dumps(payload, ensure_ascii=False) if payload is not None else ""
        self.content = body.encode("utf-8")
        self.text = body
        self.encoding = "utf-8"
        self.headers = {"content-type": "application/json; charset=utf-8"}

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

    def get(self, url, **kw):          # RobotsGate
        return ""


@pytest.fixture
def dedup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)        # cô lập RawStore ghi data/raw_html vào tmp
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    d = DedupCache(store, legacy_json_path="")
    yield d
    d.close()


def _config(token="real-token-abc", watchlist=None):
    return {
        "name": "fireant", "enabled": True, "timeout": 30, "language": "vi",
        "api": {"params": {"type": 1, "offset": 0, "limit": 20}},
        "detail": {"max_details_per_cycle": 30},
        "watchlist": watchlist or ["VIC"],
        "_secrets": {"fireant_token": token},
        "capture": {"raw_dir": "data/raw_html", "min_body_bytes": 512},
        "fuzzy_dedup": False,
    }


def _scraper(cfg, http, dedup):
    s = FireAntScraper(cfg, http, dedup)
    s.backoff = None                   # tắt sleep của SourceBackoff trong unit test
    return s


# -- hành vi cũ (giữ nguyên) ------------------------------------------------

def test_happy_path_two_step(dedup):
    http = FakeHTTP(list_payload=[LIST_POST], detail_payload=DETAIL_POST)
    result = _scraper(_config(), http, dedup).run()
    assert len(result.new) == 1
    a = result.new[0]
    assert a.url == "https://fireant.vn/dashboard/content/38267319"  # /bai-viet/ → 404
    assert a.symbols == ["VIC"]
    assert a.published_at == "2026-02-04T17:50:00+07:00"
    assert "VinWonders" in a.content_html      # detail content merged
    assert len(a.content_text) > 50


def test_missing_token_disables_scraper(dedup):
    http = FakeHTTP(list_payload=[LIST_POST])
    result = _scraper(_config(token=""), http, dedup).run()
    assert result.fetched == 0 and result.new == []
    assert http.list_calls == 0        # không gọi API khi không có token


def test_placeholder_token_disables(dedup):
    s = _scraper(_config(token="PASTE_BEARER_TOKEN_HERE"), FakeHTTP(), dedup)
    assert s.disabled


def test_token_with_bearer_prefix_stripped(dedup):
    # user dán nguyên "Bearer eyJ..." → không được nhân đôi thành "Bearer Bearer"
    s = _scraper(_config(token="Bearer eyJabc123"), FakeHTTP(), dedup)
    assert s.auth_headers["Authorization"] == "Bearer eyJabc123"
    assert not s.disabled


def test_401_self_disable_no_retry_storm(dedup):
    http = FakeHTTP(list_status=401)
    scraper = _scraper(_config(watchlist=["VIC", "HPG", "VNM"]), http, dedup)
    result = scraper.run()
    # 401 ở symbol đầu → disable ngay, KHÔNG gọi tiếp 2 symbol còn lại
    assert http.list_calls == 1
    assert scraper.disabled
    assert any("token expired" in e for e in result.errors)


def test_detail_401_keeps_article_with_summary(dedup):
    http = FakeHTTP(list_payload=[LIST_POST], detail_status=401)
    scraper = _scraper(_config(), http, dedup)
    result = scraper.run()
    assert len(result.new) == 1
    assert result.new[0].content_text == result.new[0].summary
    assert scraper.disabled


# -- Bronze capture (mới 2026-09-07) ----------------------------------------

def test_bronze_json_captured_byte_exact(dedup):
    """Response detail phải được lưu byte-exact làm Bronze artifact."""
    http = FakeHTTP(list_payload=[LIST_POST], detail_payload=DETAIL_POST)
    a = _scraper(_config(), http, dedup).run().new[0]
    cap = a.metadata["capture"]
    assert cap["capture_status"] == "ok"
    assert cap["http_status"] == 200
    raw = Path(cap["html_path"]).read_bytes()
    assert json.loads(raw.decode("utf-8"))["postID"] == 38267319
    assert hashlib.sha256(raw).hexdigest() == cap["content_sha256"]
    assert "json" in cap["response_headers"]["content-type"]


def test_silver_extracts_html_from_json_bronze(dedup):
    """SilverBuilder thấy Content-Type json → bóc `content`, KHÔNG rò key JSON."""
    http = FakeHTTP(list_payload=[LIST_POST], detail_payload=DETAIL_POST)
    cap = _scraper(_config(), http, dedup).run().new[0].metadata["capture"]
    raw = Path(cap["html_path"]).read_bytes()
    silver = SilverBuilder().build(cap, raw)
    assert "VinWonders" in silver["cleaned_text"]
    assert "postID" not in silver["cleaned_text"]     # không nuốt key JSON
    assert silver["extraction_quality"] != "empty"


def test_camelcase_source_fields(dedup):
    """Bản cũ đọc post_source (snake) nên source_name LUÔN rỗng — regression."""
    http = FakeHTTP(list_payload=[LIST_POST], detail_payload=DETAIL_POST)
    a = _scraper(_config(), http, dedup).run().new[0]
    assert a.metadata["source_name"] == "An ninh tiền tệ"
    assert a.metadata["source_url"] == "https://antt.vn/"
    assert a.metadata["language"] == "vi"


def test_auth_failure_writes_no_bronze(dedup):
    """401 ở detail: KHÔNG ghi Bronze — response lỗi auth không phải nội dung bài."""
    http = FakeHTTP(list_payload=[LIST_POST], detail_status=401)
    a = _scraper(_config(), http, dedup).run().new[0]
    assert "capture" not in a.metadata
    raw_dir = Path("data/raw_html")
    assert not raw_dir.exists() or not list(raw_dir.rglob("*.html"))


def test_empty_content_marks_partial(dedup):
    """Detail 200 nhưng `content` rỗng → Bronze vẫn lưu, gắn cờ partial."""
    http = FakeHTTP(list_payload=[LIST_POST],
                    detail_payload={**LIST_POST, "content": ""})
    a = _scraper(_config(), http, dedup).run().new[0]
    cap = a.metadata["capture"]
    assert cap["capture_status"] == "partial"
    assert "article_body" in cap["missing"]
