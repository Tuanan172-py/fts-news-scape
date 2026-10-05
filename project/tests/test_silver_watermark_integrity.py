"""Tests toàn vẹn watermark Silver — ADR 0007.

Bất biến sống còn: **không tệp Bronze nào rơi khỏi Silver mà không để lại dấu vết**.

Lỗi được vá (phát hiện 2026-09-17): `watermark_new = max(ok_ts)` chỉ lấy max của các bài
THÀNH CÔNG, trong khi `_should_process` so sánh `fetch_ts > watermark`. Một tệp lỗi có
`fetch_ts` cũ hơn một tệp thành công sẽ vĩnh viễn không bao giờ được chọn lại.
"""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.db.store import ArticleStore
from src.pipeline import derive as derive_mod
from src.pipeline.derive import rederive_incremental

_HTML = (
    "<html><body><div id='mainContent'><h1>Tiêu đề</h1>"
    + "<p>Nội dung bài viết đủ dài để bóc tách. </p>" * 20
    + "</div></body></html>"
)


def _write_bronze(raw_dir: Path, hash_: str, fetch_ts: str, *,
                  with_html: bool = True) -> str:
    """Ghi một artifact Bronze; `with_html=False` tạo tệp hỏng (raw_missing)."""
    d = raw_dir / "a.vn" / "20260917"
    d.mkdir(parents=True, exist_ok=True)
    body = _HTML.encode("utf-8")
    html_path = d / f"{hash_}.html"
    if with_html:
        html_path.write_bytes(body)
    meta = {
        "source_url": f"https://a.vn/{hash_[:6]}.html",
        "url_title_hash": hash_,
        "fetch_ts": fetch_ts,
        "render_method": "requests",
        "html_path": str(html_path),
        "content_sha256": hashlib.sha256(body).hexdigest(),
        "encoding": "utf-8",
        "images": [],
        "capture_status": "ok",
        "missing": [],
    }
    meta_path = d / f"{hash_}.meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return str(meta_path)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    raw = tmp_path / "raw_html"
    kw = {
        "raw_dir": str(raw),
        "silver_dir": str(tmp_path / "silver"),
        "package_dir": str(tmp_path / "pkg"),
    }
    return store, raw, kw


def test_failed_file_older_than_success_is_not_skipped_forever(env):
    """Hồi quy cốt lõi: tệp lỗi CŨ HƠN tệp thành công vẫn phải được thử lại.

    Trên code cũ (`watermark = max(ok_ts)`) test này thất bại: watermark nhảy lên mốc của
    tệp thành công và tệp lỗi vĩnh viễn nằm dưới ngưỡng.
    """
    store, raw, kw = env
    _write_bronze(raw, "b" * 64, "2026-09-17T10:00:00+07:00", with_html=False)  # hỏng
    _write_bronze(raw, "g" * 64, "2026-09-17T11:00:00+07:00")                   # tốt

    s1 = rederive_incremental(store, **kw)
    assert s1["failed"] >= 1, "tệp thiếu .html phải bị tính là thất bại"
    assert s1["blocking_failures"] >= 1, "phải có hàng chặn watermark trong silver_failures"

    # Watermark KHÔNG được vượt qua mốc của tệp lỗi.
    assert s1["watermark_new"] < "2026-09-17T10:00:00+07:00"

    # Chu kỳ sau vẫn phải chọn lại tệp lỗi.
    s2 = rederive_incremental(store, **kw)
    assert s2["processed"] >= 1, "tệp lỗi đã bị bỏ qua vĩnh viễn — đúng lỗi đang vá"


def test_dead_letter_after_max_attempts_unblocks_watermark(env):
    """Đủ ngưỡng lần thử → dead-letter → watermark được phép tiến, tránh nghẽn vĩnh viễn."""
    store, raw, kw = env
    _write_bronze(raw, "b" * 64, "2026-09-17T10:00:00+07:00", with_html=False)
    _write_bronze(raw, "g" * 64, "2026-09-17T11:00:00+07:00")

    for _ in range(3):
        rederive_incremental(store, max_attempts=3, **kw)

    blocking, dead = store.count_silver_failures()
    assert dead >= 1, "phải chuyển dead-letter sau khi đủ số lần thử"
    assert blocking == 0, "hàng dead-letter không được tiếp tục chặn watermark"

    s = rederive_incremental(store, max_attempts=3, **kw)
    assert s["watermark_new"] >= "2026-09-17T11:00:00+07:00", \
        "watermark phải tiến được sau khi lỗi đã dead-letter"


def test_success_clears_failure_row(env):
    """Tệp derive thành công phải bị xoá khỏi sổ lỗi, không để rác tích tụ."""
    store, raw, kw = env
    h = "c" * 64
    _write_bronze(raw, h, "2026-09-17T10:00:00+07:00", with_html=False)
    rederive_incremental(store, **kw)
    assert store.count_silver_failures()[0] >= 1

    _write_bronze(raw, h, "2026-09-17T10:00:00+07:00")      # vá lại artifact
    rederive_incremental(store, **kw)
    assert store.count_silver_failures() == (0, 0), "sổ lỗi phải sạch sau khi thành công"


def test_silver_not_ok_is_not_counted_as_success(env, monkeypatch):
    """Bài `silver_ok=False` nhưng package hợp lệ KHÔNG được tính thành công.

    Trước đây `process_meta` trả `ok` = chỉ tính package, nên bài loại này vẫn đẩy
    watermark qua và không bao giờ được derive lại.
    """
    store, raw, kw = env
    _write_bronze(raw, "d" * 64, "2026-09-17T10:00:00+07:00")

    def _fake(*_a, **_k):
        return {"article_id": "d" * 64, "ok": True, "silver_ok": False,
                "state": "NEW", "enqueue_status": "held", "errors": ["silver hỏng"]}

    monkeypatch.setattr(derive_mod, "process_meta", _fake)
    s = rederive_incremental(store, **kw)

    assert s["ok"] == 0 and s["failed"] == 1
    assert s["blocking_failures"] == 1


def test_meta_read_once_per_cycle(env, monkeypatch):
    """Mỗi `.meta.json` chỉ được đọc một lần mỗi chu kỳ (trước đây là ba)."""
    store, raw, kw = env
    for i in range(3):
        _write_bronze(raw, str(i) * 64, f"2026-09-17T1{i}:00:00+07:00")

    calls = []
    orig = derive_mod._read_fetch_ts
    monkeypatch.setattr(derive_mod, "_read_fetch_ts",
                        lambda p: (calls.append(p), orig(p))[1])

    rederive_incremental(store, **kw)
    assert len(calls) == len(set(calls)), f"có tệp bị đọc lặp: {len(calls)} lượt cho {len(set(calls))} tệp"
