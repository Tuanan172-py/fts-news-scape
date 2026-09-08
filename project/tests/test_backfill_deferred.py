"""
Tests scripts/maintenance/backfill_deferred.py — bất biến BRONZE-FIRST.

Bất biến sống còn: KHÔNG BAO GIỜ ghi content_text vào DB nếu bài chưa có Bronze artifact.
Đây chính là lý do `enrich_deferred.py` bị xoá (nó fetch rồi ghi thẳng, không tạo Bronze).
"""

import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.core.models import Article
from src.db.store import ArticleStore

_SPEC = importlib.util.spec_from_file_location(
    "backfill_deferred",
    Path(__file__).resolve().parent.parent / "scripts" / "maintenance"
    / "backfill_deferred.py")
backfill = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(backfill)

DETAIL_HTML = (
    "<html><body><div class='vnbcbc-body'>"
    "<p>" + ("Nội dung thân bài đủ dài để vượt ngưỡng kiểm tra. " * 12) + "</p>"
    "</div></body></html>"
)

BAODAUTU_HTML = (
    '<html><body><main class="main_content">'
    '<div class="title-detail">Tiêu đề</div>'
    '<span class="post-time"> - 06/09/2026 19:55</span>'
    '<div id="content_detail_news"><p>'
    + ("Thân bài đủ dài để vượt ngưỡng kiểm tra. " * 12)
    + 'Ngày 28/8/2026 có trong thân bài.</p></div>'
    '</main></body></html>'
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = str(tmp_path / "t.db")
    store = ArticleStore(db_path=db)
    a = Article(url="https://vietnambiz.vn/bai-test-123.htm",
                title="Bài test deferred",
                source_domain="vietnambiz.vn",
                summary="Tóm tắt ngắn",
                content_text="Tóm tắt ngắn",
                metadata={"language": "vi", "detail_deferred": True})
    store.insert(a)
    yield store, a, tmp_path, db


def _row(store, h):
    conn = store.connect()
    try:
        return conn.execute(
            "SELECT content_text, published_at, metadata_json FROM articles "
            "WHERE url_title_hash=?", (h,)).fetchone()
    finally:
        conn.close()


def test_no_bronze_no_write(env):
    """KHÔNG có Bronze + không --fetch → TUYỆT ĐỐI không đụng DB."""
    store, a, _, db = env
    backfill.main("vietnambiz.vn", limit=10, do_fetch=False, dry_run=False,
                  db_path=db)
    r = _row(store, a.url_title_hash)
    assert r["content_text"] == "Tóm tắt ngắn"          # nguyên vẹn
    meta = json.loads(r["metadata_json"])
    assert meta.get("detail_deferred") is True          # vẫn còn deferred
    assert "backfilled_from_bronze" not in meta


def test_backfill_from_existing_bronze(env):
    """Có Bronze → dựng lại content TỪ FILE, không chạm mạng, và gỡ cờ deferred."""
    store, a, tmp, db = env
    d = tmp / "data" / "raw_html" / "vietnambiz.vn" / "20260907"
    d.mkdir(parents=True)
    (d / f"{a.url_title_hash}.html").write_text(DETAIL_HTML, encoding="utf-8")

    backfill.main("vietnambiz.vn", limit=10, do_fetch=False, dry_run=False,
                  db_path=db)

    r = _row(store, a.url_title_hash)
    assert "Nội dung thân bài" in r["content_text"]
    assert len(r["content_text"]) > 200
    meta = json.loads(r["metadata_json"])
    assert "detail_deferred" not in meta                # cờ đã gỡ
    assert meta["backfilled_from_bronze"].endswith(f"{a.url_title_hash}.html")


def test_dry_run_writes_nothing(env):
    store, a, tmp, db = env
    d = tmp / "data" / "raw_html" / "vietnambiz.vn" / "20260907"
    d.mkdir(parents=True)
    (d / f"{a.url_title_hash}.html").write_text(DETAIL_HTML, encoding="utf-8")

    backfill.main("vietnambiz.vn", limit=10, do_fetch=False, dry_run=True,
                  db_path=db)

    r = _row(store, a.url_title_hash)
    assert r["content_text"] == "Tóm tắt ngắn"
    assert json.loads(r["metadata_json"]).get("detail_deferred") is True


def test_find_bronze_picks_latest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    h = "a" * 64
    for day in ("20260901", "20260907"):
        d = tmp_path / "data" / "raw_html" / "vietnambiz.vn" / day
        d.mkdir(parents=True)
        (d / f"{h}.html").write_text("x", encoding="utf-8")
    got = backfill._find_bronze("vietnambiz.vn", h)
    assert got is not None and "20260907" in got        # bản mới nhất
    assert backfill._find_bronze("vietnambiz.vn", "b" * 64) is None


def test_extract_from_bronze_is_pure(tmp_path):
    p = tmp_path / "x.html"
    p.write_text(DETAIL_HTML, encoding="utf-8")
    html, text = backfill._extract_from_bronze(str(p), "div.vnbcbc-body")
    assert "vnbcbc-body" in html
    assert "Nội dung thân bài" in text
    # file KHÔNG bị sửa (Bronze là WORM)
    assert p.read_text(encoding="utf-8") == DETAIL_HTML
    # selector không khớp → fallback cả trang, vẫn không raise
    html2, text2 = backfill._extract_from_bronze(str(p), "div.khong-ton-tai")
    assert text2
    # file không tồn tại → ("", "") chứ không raise
    assert backfill._extract_from_bronze(str(tmp_path / "nope.html"), "p") == ("", "")


def test_enrich_deferred_is_gone():
    """enrich_deferred.py bị xoá vì Bronze-blind — đừng thêm lại."""
    p = (Path(__file__).resolve().parent.parent / "scripts" / "maintenance"
         / "enrich_deferred.py")
    assert not p.exists(), (
        "enrich_deferred.py ghi content_text mà KHÔNG tạo Bronze artifact "
        "→ vi phạm Bronze-first. Dùng backfill_deferred.py.")


# -- khôi phục published_at + Bronze JSON ------------------------------------

def test_recover_date_from_scope_selector(tmp_path):
    """baodautu KHÔNG có <time>/meta/JSON-LD — ngày là text thuần trong span.post-time."""
    p = tmp_path / "b.html"
    p.write_text(BAODAUTU_HTML, encoding="utf-8")
    assert backfill.recover_published_at(str(p), "span.post-time") \
        == "2026-09-06T19:55:00+07:00"
    # không có scope → không tìm thấy metadata chuẩn nào → rỗng, KHÔNG bịa
    assert backfill.recover_published_at(str(p), "") == ""


def test_recover_date_prefers_standard_metadata(tmp_path):
    p = tmp_path / "m.html"
    p.write_text('<html><head>'
                 '<meta property="article:published_time" content="2026-09-07T14:30:03+07:00">'
                 '</head><body><span class="post-time"> - 01/01/2020 00:00</span>'
                 '</body></html>', encoding="utf-8")
    # meta chuẩn phải thắng text thuần
    assert backfill.recover_published_at(str(p), "span.post-time") \
        == "2026-09-07T14:30:03+07:00"


def test_recover_date_from_time_tag(tmp_path):
    p = tmp_path / "t.html"
    p.write_text('<html><body><time datetime="2026-09-07T12:48:05+0700">x</time>'
                 '</body></html>', encoding="utf-8")
    assert backfill.recover_published_at(str(p), "") == "2026-09-07T12:48:05+0700"


def test_recover_date_never_fabricates(tmp_path):
    p = tmp_path / "n.html"
    p.write_text("<html><body><p>không có ngày nào</p></body></html>", encoding="utf-8")
    assert backfill.recover_published_at(str(p), "span.post-time") == ""
    assert backfill.recover_published_at(str(tmp_path / "khong-ton-tai.html"), "") == ""


def test_extract_from_json_bronze(tmp_path):
    """Bronze của nguồn API là JSON → phải bóc trường HTML, không nuốt key JSON."""
    p = tmp_path / "j.html"          # đuôi .html nhưng NỘI DUNG là JSON (fireant)
    body = json.dumps({"postID": 42, "title": "T",
                       "content": "<p>" + ("Nội dung thật. " * 20) + "</p>"},
                      ensure_ascii=False)
    p.write_text(body, encoding="utf-8")
    html, text = backfill._extract_from_bronze(str(p), "div.khong-lien-quan")
    assert "Nội dung thật" in text
    assert "postID" not in text      # không rò key JSON


def test_dates_only_mode(env):
    """--dates-only: chỉ sửa published_at rỗng, KHÔNG đụng content.

    Dùng bài baodautu vì đó là nguồn duy nhất mà ngày CHỈ có ở trang detail
    (không <time>/meta/JSON-LD) — chính là ca mà chế độ này sinh ra để chữa.
    """
    store, _a, tmp, db = env
    bdt = Article(url="https://baodautu.vn/bai-test-d123456.html",
                  title="Bài baodautu thiếu ngày",
                  source_domain="baodautu.vn",
                  summary="Tóm tắt ngắn",
                  content_text="Tóm tắt ngắn",
                  published_at="",                     # ← cột rỗng, cần chữa
                  metadata={"language": "vi"})
    store.insert(bdt)
    d = tmp / "data" / "raw_html" / "baodautu.vn" / "20260907"
    d.mkdir(parents=True)
    (d / f"{bdt.url_title_hash}.html").write_text(BAODAUTU_HTML, encoding="utf-8")

    backfill.main("baodautu.vn", limit=10, do_fetch=False, dry_run=False,
                  db_path=db, dates_only=True)

    r = _row(store, bdt.url_title_hash)
    assert r["published_at"] == "2026-09-06T19:55:00+07:00"
    assert r["content_text"] == "Tóm tắt ngắn"      # content KHÔNG bị đụng
