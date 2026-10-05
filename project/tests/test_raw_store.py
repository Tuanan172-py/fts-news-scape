"""
Tests RawStore — byte-exact artifact, meta.json, images[] manifest, failure branches.
"""

import json
from pathlib import Path

from _fakes import FakeResponse
from src.crawler.raw_store import RawStore

FETCHED = "2026-08-13T07:36:00+07:00"


def _meta_path(cap):
    return cap["html_path"][:-len(".html")] + ".meta.json"


def test_save_ok_byte_exact_and_meta(tmp_path):
    body = "<html><body><h1>Tiêu đề</h1><p>Nội dung bài viết.</p></body></html>"
    resp = FakeResponse(body, status=200)
    store = RawStore(base_dir=str(tmp_path / "raw"))
    cap = store.save("cafef.vn", "https://cafef.vn/a.chn", "hash1", resp,
                     fetched_at=FETCHED)

    assert cap["capture_status"] == "ok"
    assert cap["http_status"] == 200
    # byte-exact
    disk = Path(cap["html_path"]).read_bytes()
    assert disk == body.encode("utf-8")
    import hashlib
    assert cap["content_sha256"] == hashlib.sha256(disk).hexdigest()
    # meta.json tồn tại + khớp
    meta = json.loads(Path(_meta_path(cap)).read_text(encoding="utf-8"))
    assert meta["source_url"] == "https://cafef.vn/a.chn"
    assert meta["content_length_bytes"] == len(body.encode("utf-8"))
    # path pattern (AC1)
    assert "cafef.vn" in cap["html_path"] and "20260813" in cap["html_path"]


def test_images_manifest_lazy_and_figcaption_no_mutation(tmp_path):
    body = (
        '<html><body><div id="mainContent">'
        '<figure><img data-src="/img/a.jpg" alt="Alt A" title="T"/>'
        '<figcaption>Ảnh minh họa</figcaption></figure>'
        '<img srcset="/img/b-320.jpg 320w, /img/b-640.jpg 640w"/>'
        '</div></body></html>'
    )
    resp = FakeResponse(body, status=200)
    store = RawStore(base_dir=str(tmp_path / "raw"))
    cap = store.save("cafef.vn", "https://cafef.vn/a.chn", "h2", resp, fetched_at=FETCHED)

    imgs = cap["images"]
    assert len(imgs) == 2
    # D2: lazy data-src resolved (absolute) + alt/caption
    assert imgs[0]["resolved_url"] == "https://cafef.vn/img/a.jpg"
    assert imgs[0]["alt"] == "Alt A"
    assert imgs[0]["caption"] == "Ảnh minh họa"
    # srcset-only → first URL
    assert imgs[1]["resolved_url"] == "https://cafef.vn/img/b-320.jpg"
    # AC7: artifact BYTE-EXACT — không swap/mutate (so sánh nguyên văn)
    disk = Path(cap["html_path"]).read_text(encoding="utf-8")
    assert disk == body
    assert 'data-src="/img/a.jpg"' in disk  # lazy attr giữ nguyên


def test_save_none_response_records_failed(tmp_path):
    store = RawStore(base_dir=str(tmp_path / "raw"))
    cap = store.save("cafef.vn", "https://cafef.vn/x.chn", "h3", None,
                     fetched_at=FETCHED, protection="bot_challenge")
    assert cap["capture_status"] == "failed"
    assert cap["error"]["type"] == "fetch_failed"
    assert cap["error"]["protection_mechanism"] == "bot_challenge"
    assert "article_body" in cap["missing"]
    # meta ghi kể cả khi fail; không có html file
    assert Path(_meta_path(cap)).exists()
    assert not Path(cap["html_path"]).exists()


def test_save_http_error_body_saved_for_inspect(tmp_path):
    resp = FakeResponse("<html>403 forbidden</html>", status=403)
    store = RawStore(base_dir=str(tmp_path / "raw"))
    cap = store.save("vietstock.vn", "https://vietstock.vn/y.htm", "h4", resp,
                     fetched_at=FETCHED)
    assert cap["capture_status"] == "failed"
    assert cap["error"]["type"] == "http_error"
    assert cap["error"]["http_status"] == 403
    assert "article_body" in cap["missing"]
    assert Path(cap["html_path"]).exists()  # partial body vẫn lưu


def test_save_404_marks_deleted_at_source(tmp_path):
    resp = FakeResponse("<html>404 not found</html>", status=404)
    store = RawStore(base_dir=str(tmp_path / "raw"))
    cap = store.save("cafef.vn", "https://cafef.vn/gone.chn", "h6", resp,
                     fetched_at=FETCHED)
    assert cap["capture_status"] == "deleted_at_source"
    assert cap["error"]["type"] == "deleted_at_source"
    assert cap["error"]["http_status"] == 404


def test_save_410_marks_deleted_at_source(tmp_path):
    resp = FakeResponse("<html>410 gone</html>", status=410)
    store = RawStore(base_dir=str(tmp_path / "raw"))
    cap = store.save("cafef.vn", "https://cafef.vn/gone2.chn", "h7", resp,
                     fetched_at=FETCHED)
    assert cap["capture_status"] == "deleted_at_source"


def test_header_subset_excludes_set_cookie(tmp_path):
    resp = FakeResponse("<html><body>x</body></html>", status=200, headers={
        "content-type": "text/html", "set-cookie": "sid=secret",
        "authorization": "Bearer x", "etag": "abc",
    })
    store = RawStore(base_dir=str(tmp_path / "raw"))
    cap = store.save("cafef.vn", "https://cafef.vn/z.chn", "h5", resp, fetched_at=FETCHED)
    hdrs = cap["response_headers"]
    assert "content-type" in hdrs and "etag" in hdrs
    assert "set-cookie" not in hdrs and "authorization" not in hdrs


def test_duong_dan_tuong_doi_duoc_neo_vao_goc_du_an_khong_theo_cwd(tmp_path, monkeypatch):
    """Chạy ở thư mục khác vẫn ghi Bronze dưới gốc dự án, meta ghi đường dẫn tương đối."""
    from src.crawler import raw_store as rs

    project = tmp_path / "project"
    elsewhere = tmp_path / "elsewhere"
    project.mkdir()
    elsewhere.mkdir()
    monkeypatch.setattr(rs, "PROJECT_ROOT", project)
    monkeypatch.setattr(rs, "resolve_project_path",
                        lambda p: p if Path(p).is_absolute() else project / p)
    monkeypatch.chdir(elsewhere)

    store = RawStore()
    cap = store.save("cafef.vn", "https://cafef.vn/a.chn", "hash9",
                     FakeResponse("<html>x</html>", status=200), fetched_at=FETCHED)

    assert Path(cap["html_path"]).is_absolute()
    assert Path(cap["html_path"]).exists() and project in Path(cap["html_path"]).parents
    assert not (elsewhere / "data").exists()
    meta = json.loads(Path(_meta_path(cap)).read_text(encoding="utf-8"))
    assert not Path(meta["html_path"]).is_absolute()
    assert (project / meta["html_path"]).exists()


def test_lan_cao_loi_khong_ghi_de_ban_cao_tot(tmp_path):
    """Cào lại thất bại (không phản hồi, 503) giữ nguyên HTML và meta của lần cào tốt."""
    store = RawStore(base_dir=str(tmp_path / "raw"))
    good = store.save("cafef.vn", "https://cafef.vn/a.chn", "h1",
                      FakeResponse("<html>tốt</html>", status=200), fetched_at=FETCHED)
    html, meta = Path(good["html_path"]), Path(_meta_path(good))
    before = (html.read_bytes(), meta.read_bytes())

    bad1 = store.save("cafef.vn", "https://cafef.vn/a.chn", "h1", None, fetched_at=FETCHED)
    bad2 = store.save("cafef.vn", "https://cafef.vn/a.chn", "h1",
                      FakeResponse("<html>lỗi</html>", status=503), fetched_at=FETCHED)

    assert bad1["capture_status"] == "failed" and bad2["capture_status"] == "failed"
    assert (html.read_bytes(), meta.read_bytes()) == before
    assert json.loads(meta.read_text(encoding="utf-8"))["capture_status"] == "ok"


def test_cao_loi_lan_dau_van_ghi_meta_that_bai(tmp_path):
    """Chưa có bản tốt thì meta thất bại vẫn được ghi để kiểm toán."""
    store = RawStore(base_dir=str(tmp_path / "raw"))
    cap = store.save("cafef.vn", "https://cafef.vn/b.chn", "h2", None, fetched_at=FETCHED)
    assert json.loads(Path(_meta_path(cap)).read_text(encoding="utf-8"))["capture_status"] == "failed"
