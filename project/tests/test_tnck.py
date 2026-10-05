"""
Tests TnckScraper — zone JSON API + Bronze full raw HTML capture.

Fixtures thật: zone list tải live, trang detail tái tạo TỪ BRONZE đã capture.

⚠️ FakeHTTP.get_json() BỎ QUA url và trả cùng list_json cho MỌI lần gọi
(tests/_fakes.py). Với 9 zone thật, fetch_list sẽ phát lại 1 zone 9 lần →
item trùng 9×. Vì vậy mọi test ở đây cấu hình **đúng 1 zone**.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from _fakes import FakeHTTP
from src.core.config import resolve_source_domain
from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.scrapers import REGISTRY
from src.scrapers.tnck import TnckScraper

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def zone_json():
    return json.loads((FIXTURES / "tnck_zone_list.json").read_text(encoding="utf-8"))


@pytest.fixture
def detail_html():
    return (FIXTURES / "tnck_detail_page.html").read_text(encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    dedup = DedupCache(store, legacy_json_path="")
    yield dedup
    dedup.close()


def _config(**over):
    cfg = {
        "name": "tnck", "enabled": True, "timeout": 30, "language": "vi",
        "api": {"zones": [1], "pages_per_cycle": 1},   # ⚠️ 1 zone — xem docstring
        "detail": {"content_selector": "div.article__body",
                   "max_details_per_cycle": 40},
        "watchlist": ["HPG", "FPT", "VNM"],
        "fuzzy_dedup": False,
    }
    cfg.update(over)
    return cfg


def _scraper(cfg, http, dedup):
    s = TnckScraper(cfg, http, dedup)
    s.backoff = None
    return s


def test_registered():
    assert REGISTRY["tnck"] is TnckScraper


def test_uses_capture_mixin():
    """Bản cũ KHÔNG có CaptureMixin → không ghi Bronze. Regression cho phase-03."""
    from src.scrapers.capture_mixin import CaptureMixin
    assert issubclass(TnckScraper, CaptureMixin)


def test_capture_happy_path(env, zone_json, detail_html):
    http = FakeHTTP(list_json=zone_json, detail_html=detail_html)
    result = _scraper(_config(), http, env).run()

    assert len(result.new) > 0
    captured = [a for a in result.new
                if a.metadata.get("capture", {}).get("capture_status") == "ok"]
    assert captured
    a = captured[0]
    # source_domain NON-www, nhưng url GIỮ host www (định danh url_title_hash)
    assert a.source_domain == "tinnhanhchungkhoan.vn"
    assert a.url.startswith("https://www.tinnhanhchungkhoan.vn/")
    assert a.published_at.endswith("+07:00")
    assert a.metadata["language"] == "vi"
    cap = a.metadata["capture"]
    assert Path(cap["html_path"]).read_text(encoding="utf-8") == detail_html  # byte-exact
    assert cap["http_status"] == 200
    assert len(a.content_text) > 0


def test_content_selector_hits(env, zone_json, detail_html):
    http = FakeHTTP(list_json=zone_json, detail_html=detail_html)
    result = _scraper(_config(), http, env).run()
    for a in result.new:
        cap = a.metadata["capture"]
        assert cap["capture_status"] == "ok"
        assert "main_content_node" not in cap.get("missing", [])
        assert "incomplete_render" not in cap.get("missing", [])


def test_epoch_number_and_string(env, zone_json, detail_html):
    """`date` là JSON NUMBER (docs cũ ghi 'string' — SAI). Phải nhận CẢ HAI.

    Test thẳng parse_item để khỏi vướng dedup (chạy run() 2 lần thì lần sau new=0).
    """
    scraper = _scraper(_config(), FakeHTTP(list_json=zone_json,
                                           detail_html=detail_html), env)
    items = zone_json["data"]["contents"]
    assert isinstance(items[0]["date"], int), "fixture phải giữ date dạng NUMBER"

    for raw in items:
        as_int = scraper.parse_item(dict(raw, date=int(raw["date"])))
        as_str = scraper.parse_item(dict(raw, date=str(raw["date"])))
        assert as_int.published_at == as_str.published_at
        assert as_int.published_at.endswith("+07:00")


def test_zone_name_becomes_category(env, zone_json, detail_html):
    http = FakeHTTP(list_json=zone_json, detail_html=detail_html)
    result = _scraper(_config(), http, env).run()
    expected = {(c.get("zone") or {}).get("name")
                for c in zone_json["data"]["contents"]}
    got = {a.categories[0] for a in result.new if a.categories}
    assert got and got <= expected
    assert all(a.metadata.get("zone_id") not in (None, "") for a in result.new)


def test_bad_date_does_not_raise(env, zone_json, detail_html):
    payload = json.loads(json.dumps(zone_json))
    payload["data"]["contents"][0]["date"] = "not-a-number"
    http = FakeHTTP(list_json=payload, detail_html=detail_html)
    result = _scraper(_config(), http, env).run()
    assert result.new                       # không crash
    assert any(a.published_at == "" for a in result.new)


def test_missing_fields_skipped(env, zone_json, detail_html):
    payload = json.loads(json.dumps(zone_json))
    payload["data"]["contents"][0]["title"] = ""
    payload["data"]["contents"][1]["url"] = ""
    http = FakeHTTP(list_json=payload, detail_html=detail_html)
    result = _scraper(_config(), http, env).run()
    n_valid = len(payload["data"]["contents"]) - 2
    assert len(result.new) == n_valid


def test_detail_failure_keeps_summary(env, zone_json):
    http = FakeHTTP(list_json=zone_json, detail_html=None)
    result = _scraper(_config(), http, env).run()
    assert len(result.new) > 0
    for a in result.new:
        assert a.metadata["capture"]["capture_status"] == "failed"
        assert a.content_text == a.summary
    assert any("detail fetch failed" in e for e in result.errors)


def test_zone_fetch_failure_isolated(env, detail_html):
    """API trả None → error, KHÔNG raise (graceful degradation)."""
    http = FakeHTTP(list_json=None, detail_html=detail_html)
    result = _scraper(_config(), http, env).run()
    assert result.new == []
    assert any("fetch failed" in e for e in result.errors)


def test_max_details_cap(env, zone_json, detail_html):
    cfg = _config(detail={"content_selector": "div.article__body",
                          "max_details_per_cycle": 1})
    http = FakeHTTP(list_json=zone_json, detail_html=detail_html)
    result = _scraper(cfg, http, env).run()
    assert http.detail_calls == 1
    assert any(a.metadata.get("detail_deferred") for a in result.new)


# -- host resolution fix (phase-03) -----------------------------------------

def test_resolve_source_domain():
    """Bẫy cũ: f'{dom}.vn' biến 'tnck' → 'tnck.vn' (không khớp gì) → report 0 articles."""
    assert resolve_source_domain("tnck") == "tinnhanhchungkhoan.vn"
    assert resolve_source_domain("cafef") == "cafef.vn"            # schema.yaml
    assert resolve_source_domain("vietnambiz") == "vietnambiz.vn"  # schema.yaml
    assert resolve_source_domain("cafef.vn") == "cafef.vn"         # đã là host
    assert resolve_source_domain("khong-ton-tai") == "khong-ton-tai.vn"  # fallback legacy


def test_config_zones_match_plan():
    """Config thật phải giữ đúng 9 zone đã chốt, và KHÔNG chứa zone PR/hoãn."""
    import yaml
    p = Path(__file__).resolve().parent.parent / "config" / "domains" / "tnck.yaml"
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert cfg["enabled"] is True
    assert cfg["method"] == "tnck"
    assert cfg["api"]["zones"] == [1, 4, 6, 11, 21, 26, 29, 33, 39]
    assert cfg["api"]["pages_per_cycle"] == 1
    for pr_zone in (8, 27, 45, 32, 16, 14):      # PR / hoãn / tạp
        assert pr_zone not in cfg["api"]["zones"]
    assert cfg["detail"]["content_selector"] == "div.article__body"
    assert cfg["compliance"]["respect_robots"] is True
