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
