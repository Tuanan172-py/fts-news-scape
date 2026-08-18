"""
Bug fixes tồn đọng — Silver extraction robustness (#2), silver validate gate (#3),
lang/domain hardening (#4), refresh-driven change-detection (#1).
"""

from __future__ import annotations

import json

from _fakes import FakeHTTP

from src.crawler.raw_store import RawStore
from src.db.store import ArticleStore
from src.handoff.catalog import Catalog
from src.pipeline.refresh import refresh_row, select_watchlist
from src.pipeline.run import process_meta
from src.pipeline.silver_builder import SilverBuilder, _detect_lang
from src.handoff.contract_validator import validate as schema_validate

_ARTICLE_HTML = ("<html><body><article><h1>Tiêu đề bài</h1>"
                 "<p>" + "Nội dung bài viết đầy đủ về thị trường chứng khoán Việt Nam. " * 8 +
                 "</p></article></body></html>")


def _meta(hash_="h1", domain="cafef.vn", html_path=None):
    return {
        "url_title_hash": hash_,
        "source_url": f"https://{domain}/x.chn",
        "html_path": html_path or f"data/raw_html/{domain}/20260817/{hash_}.html",
        "content_sha256": "abc", "fetch_ts": "2026-08-17T00:00:00+07:00",
        "capture_status": "ok", "missing": [], "images": [], "encoding": "utf-8",
    }


# -- #2 Silver extraction robustness + quality ------------------------------
def test_silver_extraction_quality_and_valid():
    silver = SilverBuilder().build(_meta(), _ARTICLE_HTML.encode("utf-8"))
    assert silver["cleaned_text"].strip()
    assert silver["extraction_quality"] in ("high", "medium", "low")
    ok, errs = schema_validate(silver, "silver-v1")
    assert ok, errs


def test_silver_empty_body_marked_empty_and_invalid():
    silver = SilverBuilder().build(_meta("e1"), b"<html><body></body></html>")
    assert silver["cleaned_text"] == ""
    assert silver["extraction_quality"] == "empty"
    ok, _ = schema_validate(silver, "silver-v1")
    assert ok is False  # minLength gate


# -- #4 lang + domain -------------------------------------------------------
def test_detect_lang():
    assert _detect_lang("Thị trường chứng khoán tăng điểm mạnh mẽ") == "vi"
    assert _detect_lang("The market rose today on strong earnings and demand") == "en"
    assert _detect_lang("1234567890 ---- ====") == "und"


def test_domain_fallback_from_source_url():
    m = _meta()
    m["html_path"] = ""   # path rỗng (đổi thư mục base) → fallback netloc + strip www.
    m["source_url"] = "https://www.vietstock.vn/2026/08/a.htm"
    silver = SilverBuilder().build(m, _ARTICLE_HTML.encode("utf-8"))
    assert silver["domain"] == "vietstock.vn"


# -- #3 silver validate gate → held ----------------------------------------
def test_process_meta_holds_on_empty_silver(tmp_path):
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    raw = tmp_path / "e1.html"
    raw.write_bytes(b"<html><body></body></html>")
    meta = _meta("e1", html_path=str(raw))
    metap = tmp_path / "e1.meta.json"
    metap.write_text(json.dumps(meta), encoding="utf-8")

    res = process_meta(store, str(metap), silver_dir=str(tmp_path / "s"),
                       package_dir=str(tmp_path / "p"))
    assert res["silver_ok"] is False
    assert res["enqueue_status"] == "held"
    assert Catalog(store).counts().get("held") == 1


# -- #1 change-detection fires on a 2nd capture -----------------------------
def _save_capture(raw_store, hash_, html, fetched_at):
    from _fakes import FakeResponse
    return raw_store.save("cafef.vn", "https://cafef.vn/x.chn", hash_,
                          FakeResponse(html), fetched_at=fetched_at)


def test_refresh_triggers_content_changed(tmp_path):
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    raw_store = RawStore(str(tmp_path / "raw"))
    sd, pd = str(tmp_path / "s"), str(tmp_path / "p")

    v1 = "<html><body><article><h1>T</h1><p>" + "alpha " * 60 + "</p></article></body></html>"
    v2 = "<html><body><article><h1>T</h1><p>" + "beta " * 60 + "</p></article></body></html>"

    cap1 = _save_capture(raw_store, "h1", v1, "2026-08-16T00:00:00+07:00")
    r1 = process_meta(store, cap1["html_path"][:-5] + ".meta.json", silver_dir=sd, package_dir=pd)
    assert r1["state"] == "NEW"

    cap2 = _save_capture(raw_store, "h1", v2, "2026-08-17T00:00:00+07:00")
    r2 = process_meta(store, cap2["html_path"][:-5] + ".meta.json", silver_dir=sd, package_dir=pd)
    assert r2["state"] == "CONTENT_CHANGED"


# -- #1 refresh_row wiring --------------------------------------------------
def test_refresh_row_ok(tmp_path):
    raw_store = RawStore(str(tmp_path / "raw"))
    http = FakeHTTP(detail_html=_ARTICLE_HTML, detail_status=200)
    row = {"url": "https://cafef.vn/x.chn", "url_title_hash": "h1", "source_domain": "cafef.vn"}
    res = refresh_row(http, raw_store, None, row, fetched_at="2026-08-17T00:00:00+07:00")
    assert res["capture_status"] == "ok"
    assert res["meta_path"].endswith(".meta.json")
    assert http.detail_calls == 1


def test_refresh_row_robots_skip(tmp_path):
    raw_store = RawStore(str(tmp_path / "raw"))
    http = FakeHTTP(detail_html=_ARTICLE_HTML)

    class _Deny:
        def allowed(self, url):  # noqa: D401
            return False

    row = {"url": "https://cafef.vn/x.chn", "url_title_hash": "h1", "source_domain": "cafef.vn"}
    res = refresh_row(http, raw_store, _Deny(), row)
    assert res["capture_status"] == "skipped_robots"
    assert http.detail_calls == 0


def test_select_watchlist(tmp_path):
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    conn = store.connect()
    conn.executemany(
        "INSERT INTO articles (url, url_title_hash, title, source_domain, fetched_at) "
        "VALUES (?,?,?,?,?)",
        [("https://cafef.vn/a.chn", "a", "A", "cafef.vn", "2026-08-16T00:00:00+07:00"),
         ("https://cafef.vn/b.chn", "b", "B", "cafef.vn", "2026-08-17T00:00:00+07:00")])
    conn.commit()
    conn.close()
    rows = select_watchlist(store, limit=10)
    assert [r["url_title_hash"] for r in rows] == ["b", "a"]  # newest first
