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

from _fakes import FakeResponse
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


class _FakeHTTP:
    """HTTPClient giả cho đường backfill — đếm số lần thực sự chạm mạng."""

    def __init__(self, status=404, body="<html>gone</html>"):
        self.status = status
        self.body = body
        self.calls = 0

    def get_response(self, url, **kw):
        self.calls += 1
        return FakeResponse(self.body, status=self.status)

    def get(self, url, **kw):
        return ""


def _patch_net(monkeypatch, fake):
    monkeypatch.setattr(backfill, "HTTPClient", lambda **kw: fake)
    monkeypatch.setattr(backfill, "RobotsGate", lambda http: None)   # None → bỏ qua robots


def test_retry_404_marks_source_deleted_and_stops_requerying(env, monkeypatch):
    """Hồi quy US-011: retry gặp 404 PHẢI ghi cờ source_deleted xuống DB.

    Không ghi thì `_DEFERRED_WHERE` chọn lại row ở mọi chu kỳ sau → job tự động (5
    phút/lần) fetch một URL đã chết vĩnh viễn, ~288 request rác/ngày/bài.
    """
    store, a, _tmp, db = env
    fake = _FakeHTTP(status=404)
    _patch_net(monkeypatch, fake)

    backfill.main("vietnambiz.vn", limit=10, do_fetch=True, dry_run=False, db_path=db)

    meta = json.loads(_row(store, a.url_title_hash)["metadata_json"])
    assert meta.get("source_deleted") is True
    assert meta["capture_retry"]["attempts"] == 1
    assert meta["capture_retry"]["last_status"] == 404
    assert fake.calls == 1

    backfill.main("vietnambiz.vn", limit=10, do_fetch=True, dry_run=False, db_path=db)
    assert fake.calls == 1, "bài đã bị nguồn xóa vẫn bị fetch lại → vòng lặp vô hạn"


def test_transient_failure_gives_up_after_max_attempts(env, monkeypatch):
    """Lỗi tạm thời lặp lại đủ ngưỡng → capture_giveup, ngừng truy đuổi."""
    store, a, _tmp, db = env
    fake = _FakeHTTP(status=500)
    _patch_net(monkeypatch, fake)

    for _ in range(6):
        backfill.main("vietnambiz.vn", limit=10, do_fetch=True, dry_run=False,
                      db_path=db, max_attempts=3)

    meta = json.loads(_row(store, a.url_title_hash)["metadata_json"])
    assert meta.get("capture_giveup") is True
    assert meta.get("source_deleted") is None      # lỗi tạm thời KHÁC bị xóa
    assert fake.calls == 3, "phải dừng đúng sau max_attempts lần thử"


def test_dry_run_records_no_attempt(env, monkeypatch):
    """--dry-run không được ghi sổ retry (giữ đúng ngữ nghĩa 'không đụng DB')."""
    store, a, _tmp, db = env
    _patch_net(monkeypatch, _FakeHTTP(status=404))

    backfill.main("vietnambiz.vn", limit=10, do_fetch=True, dry_run=True, db_path=db)

    meta = json.loads(_row(store, a.url_title_hash)["metadata_json"])
    assert "capture_retry" not in meta and "source_deleted" not in meta


def test_backoff_wraps_every_fetch(env, monkeypatch):
    """Đường backfill phải đi qua SourceBackoff như đường capture sống."""
    _store, _a, _tmp, db = env
    _patch_net(monkeypatch, _FakeHTTP(status=404))
    seen = []

    class _SpyBackoff:
        def before_fetch(self, dom):
            seen.append(("before", dom))

        def observe(self, dom, status):
            seen.append(("observe", dom, status))

    monkeypatch.setattr(backfill, "SourceBackoff", _SpyBackoff)
    backfill.main("vietnambiz.vn", limit=10, do_fetch=True, dry_run=False, db_path=db)

    assert seen == [("before", "vietnambiz.vn"), ("observe", "vietnambiz.vn", 404)]


def test_mode_failed_recovers_transient_failure_from_bronze(env):
    """`--mode failed`: bài lỗi tạm thời lúc capture sống được khôi phục từ Bronze.

    Trước US-012 nhóm này KHÔNG bao giờ được thử lại — một lần timeout là mất toàn văn
    vĩnh viễn, chỉ còn summary.
    """
    store, deferred_article, tmp, db = env
    failed = Article(url="https://vietnambiz.vn/bai-loi-tam-thoi.htm",
                     title="Bài lỗi tạm thời",
                     source_domain="vietnambiz.vn",
                     summary="Tóm tắt",
                     content_text="Tóm tắt",
                     metadata={"language": "vi",
                               "capture": {"capture_status": "failed",
                                           "http_status": 503}})
    store.insert(failed)
    d = tmp / "data" / "raw_html" / "vietnambiz.vn" / "20260907"
    d.mkdir(parents=True)
    (d / f"{failed.url_title_hash}.html").write_text(DETAIL_HTML, encoding="utf-8")

    backfill.main("vietnambiz.vn", limit=10, do_fetch=False, dry_run=False,
                  db_path=db, mode="failed")

    r = _row(store, failed.url_title_hash)
    assert "Nội dung thân bài" in r["content_text"]
    meta = json.loads(r["metadata_json"])
    assert "backfilled_from_bronze" in meta

    # mode=failed KHÔNG được đụng tới bài thuộc nhóm deferred
    assert json.loads(_row(store, deferred_article.url_title_hash)["metadata_json"]) \
        .get("detail_deferred") is True

    # đã khôi phục xong → không bị chọn lại ở lần quét sau
    conn = store.connect()
    again = conn.execute(
        f"SELECT url_title_hash FROM articles WHERE {backfill._FAILED_WHERE}").fetchall()
    conn.close()
    assert not any(x["url_title_hash"] == failed.url_title_hash for x in again)


def test_deferred_where_excludes_source_deleted(env):
    """Bài đã xác nhận bị nguồn xóa (404/410) KHÔNG được truy vấn _DEFERRED_WHERE
    chọn lại — tránh backfill retry vô ích một URL vĩnh viễn đã biến mất."""
    store, a, _, _db = env
    conn = store.connect()
    rows = conn.execute(
        f"SELECT url_title_hash FROM articles WHERE {backfill._DEFERRED_WHERE}").fetchall()
    assert any(r["url_title_hash"] == a.url_title_hash for r in rows)

    meta = json.loads(_row(store, a.url_title_hash)["metadata_json"])
    meta["source_deleted"] = True
    conn.execute("UPDATE articles SET metadata_json=? WHERE url_title_hash=?",
                 (json.dumps(meta, ensure_ascii=False), a.url_title_hash))
    conn.commit()

    rows2 = conn.execute(
        f"SELECT url_title_hash FROM articles WHERE {backfill._DEFERRED_WHERE}").fetchall()
    assert not any(r["url_title_hash"] == a.url_title_hash for r in rows2)
    conn.close()


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


def test_find_bronze_rejects_error_page_artifact(tmp_path, monkeypatch):
    """Artifact của TRANG LỖI không được dùng để dựng lại nội dung bài.

    RawStore vẫn ghi body khi HTTP lỗi; nếu không soi sidecar thì backfill sẽ bóc chữ
    trong trang 404/500 ra làm content_text của bài.
    """
    monkeypatch.chdir(tmp_path)
    h = "c" * 64
    d = tmp_path / "data" / "raw_html" / "vietnambiz.vn" / "20260917"
    d.mkdir(parents=True)
    (d / f"{h}.html").write_text("<html>404 not found</html>", encoding="utf-8")
    meta = d / f"{h}.meta.json"

    meta.write_text(json.dumps({"capture_status": "deleted_at_source"}), encoding="utf-8")
    assert backfill._find_bronze("vietnambiz.vn", h) is None

    meta.write_text(json.dumps({"capture_status": "failed"}), encoding="utf-8")
    assert backfill._find_bronze("vietnambiz.vn", h) is None

    meta.write_text(json.dumps({"capture_status": "ok"}), encoding="utf-8")
    assert backfill._find_bronze("vietnambiz.vn", h) is not None


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
