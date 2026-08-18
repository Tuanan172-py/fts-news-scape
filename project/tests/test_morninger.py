"""
Morninger tests — pipeline_state, incremental re-derive watermark/checkpoint, scheduler jobs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.db.store import ArticleStore
from src.morninger import build_scheduler
from src.pipeline.derive import rederive_incremental
from src.pipeline.drift import list_drift

_HTML = (
    "<html><body><div id='mainContent'><h1>Tiêu đề</h1>"
    + "<p>Nội dung bài viết đủ dài để bóc tách. </p>" * 20
    + "</div></body></html>"
)


def _write_bronze(
    raw_dir: Path,
    domain: str,
    yyyymmdd: str,
    hash_: str,
    fetch_ts: str,
    *,
    with_html: bool = True,
) -> str:
    """Ghi 1 Bronze artifact (html + meta.json). Trả meta_path."""
    d = raw_dir / domain / yyyymmdd
    d.mkdir(parents=True, exist_ok=True)
    body = _HTML.encode("utf-8")
    sha = hashlib.sha256(body).hexdigest()
    html_path = d / f"{hash_}.html"
    meta_path = d / f"{hash_}.meta.json"
    if with_html:
        html_path.write_bytes(body)
    meta = {
        "source_url": f"https://{domain}/a-{hash_[:6]}.html",
        "url_title_hash": hash_,
        "fetch_ts": fetch_ts,
        "render_method": "requests",
        "html_path": str(html_path),
        "content_sha256": sha,
        "encoding": "utf-8",
        "images": [],
        "capture_status": "ok",
        "missing": [],
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return str(meta_path)


def _version_count(store, hash_: str) -> int:
    conn = store._connect()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM article_versions WHERE url_title_hash=?", (hash_,)
        ).fetchone()[0]
    finally:
        conn.close()


@pytest.fixture
def store(tmp_path):
    return ArticleStore(db_path=str(tmp_path / "t.db"))


@pytest.fixture
def derive_kw(tmp_path):
    raw = tmp_path / "raw_html"
    return {
        "raw_dir": str(raw),
        "silver_dir": str(tmp_path / "silver"),
        "package_dir": str(tmp_path / "pkg"),
    }


# -- pipeline_state ----------------------------------------------------------
def test_pipeline_state_roundtrip(store):
    assert store.get_state("silver_watermark") is None
    store.set_state("silver_watermark", "2026-08-17T09:00:00+07:00")
    assert store.get_state("silver_watermark") == "2026-08-17T09:00:00+07:00"
    store.set_state("silver_watermark", "2026-08-17T10:00:00+07:00")  # overwrite
    assert store.get_state("silver_watermark") == "2026-08-17T10:00:00+07:00"


# -- incremental re-derive ---------------------------------------------------
def test_rederive_processes_new_and_checkpoint(tmp_path, store, derive_kw):
    raw = Path(derive_kw["raw_dir"])
    _write_bronze(raw, "a.vn", "20260817", "h1", "2026-08-17T08:00:00+07:00")
    _write_bronze(raw, "a.vn", "20260817", "h2", "2026-08-17T09:00:00+07:00")

    s = rederive_incremental(store, **derive_kw)
    assert s["processed"] == 2 and s["ok"] == 2
    assert s["watermark_new"] == "2026-08-17T09:00:00+07:00"
    assert s["backlog"] == 0 and s["checkpoint_reached"] is True
    assert store.get_state("silver_watermark") == "2026-08-17T09:00:00+07:00"
    assert store.get_state("silver_checkpoint") == "2026-08-17T09:00:00+07:00"


def test_rederive_skips_already_processed(tmp_path, store, derive_kw):
    raw = Path(derive_kw["raw_dir"])
    _write_bronze(raw, "a.vn", "20260817", "h1", "2026-08-17T08:00:00+07:00")
    rederive_incremental(store, **derive_kw)
    assert _version_count(store, "h1") == 1

    # thêm 1 bài MỚI (fetch_ts lớn hơn watermark)
    _write_bronze(raw, "a.vn", "20260817", "h2", "2026-08-17T09:00:00+07:00")
    s = rederive_incremental(store, **derive_kw)
    assert s["processed"] == 1 and s["ok"] == 1  # chỉ bài mới
    assert s["watermark_new"] == "2026-08-17T09:00:00+07:00"
    assert _version_count(store, "h1") == 1  # h1 không bị xử lý lại


def test_rederive_idempotent_noop(tmp_path, store, derive_kw):
    raw = Path(derive_kw["raw_dir"])
    _write_bronze(raw, "a.vn", "20260817", "h1", "2026-08-17T08:00:00+07:00")
    s1 = rederive_incremental(store, **derive_kw)
    s2 = rederive_incremental(store, **derive_kw)  # không có file mới
    assert s1["ok"] == 1 and s2["processed"] == 0
    assert s2["watermark_new"] == s1["watermark_new"]
    assert s2["backlog"] == 0 and s2["checkpoint_reached"] is True


def test_raw_missing_does_not_advance_watermark(tmp_path, store, derive_kw):
    raw = Path(derive_kw["raw_dir"])
    _write_bronze(
        raw, "a.vn", "20260817", "h1", "2026-08-17T08:00:00+07:00", with_html=False
    )  # meta nhưng thiếu .html
    s = rederive_incremental(store, **derive_kw)
    assert s["processed"] == 1 and s["ok"] == 0  # raw_missing
    assert s["watermark_new"] == ""  # không tiến watermark
    assert s["backlog"] == 1 and s["checkpoint_reached"] is False


def test_missing_fetch_ts_always_retried(tmp_path, store, derive_kw):
    raw = Path(derive_kw["raw_dir"])
    meta = _write_bronze(raw, "a.vn", "20260817", "h1", "2026-08-17T08:00:00+07:00")
    # ghi đè fetch_ts thành rỗng → corrupt, phải được xử lý lại mỗi lần chạy
    d = json.loads(Path(meta).read_text(encoding="utf-8"))
    d["fetch_ts"] = ""
    Path(meta).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    rederive_incremental(store, **derive_kw)
    s = rederive_incremental(store, **derive_kw)  # re-run vẫn xử lý lại
    assert s["processed"] == 1


# -- drift ---------------------------------------------------------------
def test_list_drift_empty(store):
    assert list_drift(store) == []


# -- silver manifest -----------------------------------------------------
def test_silver_manifest_at_checkpoint(tmp_path, store, derive_kw):
    from src.export.silver_manifest import export_silver_manifest

    raw = Path(derive_kw["raw_dir"])
    _write_bronze(raw, "a.vn", "20260817", "h1", "2026-08-17T08:00:00+07:00")
    s = rederive_incremental(store, **derive_kw)
    assert s["checkpoint_reached"] is True

    out = tmp_path / "silver.csv"
    path, n = export_silver_manifest(store, out=str(out))
    assert n == 1 and Path(path) == out
    text = out.read_text(encoding="utf-8-sig")
    header = text.splitlines()[0].split(",")
    assert header[:2] == ["article_id", "domain"]
    row = text.splitlines()[1]
    assert "h1" in row and "a.vn" in row and "NEW" in row and "pending" in row


# -- scheduler -----------------------------------------------------------


def test_scheduler_fires_jobs_automatically():
    """Smoke: interval job (coalesce + max_instances=1 như build_scheduler) tự chạy
    lặp lại theo lịch mà không cần trigger thủ công."""
    import time

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    fired: list[str] = []
    sched = BackgroundScheduler()
    sched.add_job(
        lambda: fired.append("tick"),
        IntervalTrigger(seconds=1),
        coalesce=True,
        max_instances=1,
    )
    sched.start()
    try:
        time.sleep(2.4)
    finally:
        sched.shutdown(wait=False)
    assert len(fired) >= 2, f"job fired only {len(fired)} times"


def test_build_scheduler_jobs():
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    calls = []
    cfg = {
        "capture_interval_minutes": 5,
        "rederive_interval_minutes": 10,
        "drift_hour": 7,
        "drift_minute": 30,
        "drift_limit": 50,
    }
    sched = build_scheduler(
        lambda: calls.append("capture"),
        lambda: calls.append("derive"),
        lambda: calls.append("drift"),
        cfg,
    )
    jobs = {j.id: j for j in sched.get_jobs()}
    assert set(jobs) == {"capture", "derive", "drift"}

    cap = jobs["capture"]
    assert isinstance(cap.trigger, IntervalTrigger)
    assert cap.trigger.interval.total_seconds() == 5 * 60
    assert cap.coalesce is True and cap.max_instances == 1

    der = jobs["derive"]
    assert isinstance(der.trigger, IntervalTrigger)
    assert der.trigger.interval.total_seconds() == 10 * 60
    assert der.coalesce is True and der.max_instances == 1

    drift = jobs["drift"]
    assert isinstance(drift.trigger, CronTrigger)
    fields = {f.name: f for f in drift.trigger.fields}
    assert "7" in str(fields["hour"]) and "30" in str(fields["minute"])
    assert drift.coalesce is True and drift.max_instances == 1
