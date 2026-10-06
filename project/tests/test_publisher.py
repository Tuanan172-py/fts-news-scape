"""Kiểm thử publisher một chiều: tắt khi thiếu đích, giao thức chép, manifest và probe."""

from __future__ import annotations

import json
import os
import tarfile
import time
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from src.core.models import Article
from src.db.store import ArticleStore
from src.export import publisher as pub
from src.ops.probes import probe_publish

DAY = date(2026, 10, 4)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Dựng gốc dữ liệu tạm có DB nhỏ, Bronze, tệp giao hàng và một đích xuất bản tạm."""
    data = tmp_path / "data"
    target = tmp_path / "publish"
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(data))
    monkeypatch.delenv(pub.PUBLISH_DIR_ENV, raising=False)
    db = data / "monocle.db"
    store = ArticleStore(db_path=db)
    for i, ts in enumerate(("2026-10-04T08:00:00+07:00", "2026-10-04T21:30:00+07:00",
                            "2026-10-05T07:00:00+07:00")):
        store.insert(Article(url=f"https://a.vn/{i}", title=f"Bài {i}", source_domain="a.vn",
                             content_html="<p>nặng</p>", content_text="nội dung",
                             fetched_at=ts))
    store.insert_agent_output({"article_id": "x1", "raw_sha256": "s", "output_json": "{}",
                               "dod_pass": 1, "created_at": "2026-10-04T10:00:00+07:00"})
    store.insert_l1_output({"article_id": "x1", "output_json": "{}", "dod_pass": 1,
                            "created_at": "2026-10-04T10:00:00+07:00"})
    bronze = data / "raw_html" / "a.vn" / "20261004"
    bronze.mkdir(parents=True)
    (bronze / "h1.html").write_text("<html>1</html>", encoding="utf-8")
    (bronze / "h1.meta.json").write_text('{"url": "https://a.vn/0"}', encoding="utf-8")
    (data / "raw_html" / "b.vn" / "20261005").mkdir(parents=True)
    (data / "raw_html" / "b.vn" / "20261005" / "z.html").write_text("x", encoding="utf-8")
    user = data / "users_output" / "an"
    user.mkdir(parents=True)
    (user / "2026-10-04.xlsx").write_bytes(b"xlsx-bytes")
    return {"data": data, "target": target, "db": db}


def _run(env, **kw):
    """Gọi publish_day với DB và đích của fixture."""
    kw.setdefault("target", env["target"])
    return pub.publish_day(DAY, db_path=env["db"], keep_review_days=7, **kw)


def _all_files(root: Path) -> list[Path]:
    """Liệt kê mọi tệp dưới một thư mục."""
    return sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []


def test_disabled_without_env(env):
    res = pub.publish_day(DAY, db_path=env["db"])
    assert res.status == "disabled"
    assert not env["target"].exists()
    assert not (env["data"] / "publish_staging").exists()


def test_dry_run_writes_nothing(env):
    res = _run(env, dry_run=True)
    assert res.status == "ok"
    kinds = sorted({f.kind for f in res.files})
    assert kinds == ["bronze", "parquet", "review", "users"]
    assert all(f.action == "planned" for f in res.files)
    assert not env["target"].exists()
    assert not (env["data"] / "publish_staging").exists()


def test_publish_all_kinds_and_manifest_matches(env):
    res = _run(env)
    assert res.status == "ok", res.message
    t = env["target"]
    manifest = json.loads((t / "_manifest" / "20261004.json").read_text(encoding="utf-8"))
    paths = {f["path"]: f for f in manifest["files"]}
    assert "review/monocle_review_20261004.db" in paths
    assert "bronze/2026/10/04/a.vn.tar.xz" in paths
    assert not any("b.vn" in p for p in paths)
    assert "users/output/an/2026-10-04.xlsx" in paths
    art = "parquet/articles/year=2026/month=10/part-20261004.parquet"
    assert paths[art]["rows"] == 2
    assert paths["parquet/analysis/year=2026/month=10/part-20261004.parquet"]["rows"] == 1
    assert paths["parquet/mentions/year=2026/month=10/part-20261004.parquet"]["rows"] == 1
    for rel, f in paths.items():
        assert pub.sha256_file(t / rel) == f["sha256"]
        assert (t / rel).stat().st_size == f["size"]
    cols = pq.read_table(t / art).column_names
    assert "content_html" not in cols and "content_text" in cols
    members = paths["bronze/2026/10/04/a.vn.tar.xz"]["members"]
    assert sorted(m["name"] for m in members) == ["a.vn/20261004/h1.html",
                                                 "a.vn/20261004/h1.meta.json"]
    with tarfile.open(t / "bronze/2026/10/04/a.vn.tar.xz", "r:xz") as tar:
        assert sorted(tar.getnames()) == sorted(m["name"] for m in members)
    assert not [p for p in _all_files(t) if p.name.endswith(".partial")]
    assert not (env["data"] / "publish_staging" / "20261004").exists()


def test_rerun_does_not_overwrite(env):
    assert _run(env).status == "ok"
    before = {p: (p.stat().st_mtime_ns, pub.sha256_file(p)) for p in _all_files(env["target"])
              if p.name != "latest.json"}
    res = _run(env)
    assert res.status == "ok" and "không làm lại" in res.message
    forced = _run(env, force=True)
    assert forced.status == "ok", forced.message
    assert all(f.action == "skipped" for f in forced.files)
    after = {p: (p.stat().st_mtime_ns, pub.sha256_file(p)) for p in _all_files(env["target"])
             if p.name != "latest.json"}
    assert after == before


def test_resume_after_partial_run(env):
    assert _run(env).status == "ok"
    t = env["target"]
    (t / "users/output/an/2026-10-04.xlsx").unlink()
    res = _run(env)
    assert res.status == "ok", res.message
    assert (t / "users/output/an/2026-10-04.xlsx").read_bytes() == b"xlsx-bytes"


def test_conflicting_target_is_reported_not_overwritten(env):
    dst = env["target"] / "users/output/an/2026-10-04.xlsx"
    dst.parent.mkdir(parents=True)
    dst.write_bytes(b"khac")
    res = _run(env)
    assert res.status == "partial"
    bad = [f for f in res.files if f.action == "conflict"]
    assert [f.path for f in bad] == ["users/output/an/2026-10-04.xlsx"]
    assert dst.read_bytes() == b"khac"
    assert not (env["target"] / "_manifest" / "20261004.json").exists()
    assert not (env["target"] / "_manifest" / "latest.json").exists()


def test_latest_written_last(env, monkeypatch):
    order: list[str] = []
    real_copy, real_latest = pub.copy_no_overwrite, pub._write_json_replace

    def spy_copy(src, dst, sha=None):
        order.append(Path(dst).name)
        return real_copy(src, dst, sha)

    def spy_latest(path, data):
        order.append(Path(path).name)
        return real_latest(path, data)

    monkeypatch.setattr(pub, "copy_no_overwrite", spy_copy)
    monkeypatch.setattr(pub, "_write_json_replace", spy_latest)
    assert _run(env).status == "ok"
    assert order[-1] == "latest.json"
    assert order[-2] == "20261004.json"
    latest = json.loads((env["target"] / "_manifest/latest.json").read_text(encoding="utf-8"))
    assert latest["manifest"] == "_manifest/20261004.json"


def test_review_retention_only_removes_own_reviews(env):
    t = env["target"]
    foreign = t / "review" / "monocle_review_20200101.db"
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b"cua nguoi khac")
    for d in (date(2026, 10, 2), date(2026, 10, 3), DAY):
        res = pub.publish_day(d, db_path=env["db"], keep_review_days=2, target=t)
        assert res.status == "ok", res.message
    assert not (t / "review/monocle_review_20261002.db").exists()
    assert (t / "review/monocle_review_20261003.db").exists()
    assert (t / "review/monocle_review_20261004.db").exists()
    assert foreign.exists()
    again = pub.publish_day(date(2026, 10, 2), db_path=env["db"], keep_review_days=2, target=t)
    assert again.status == "ok" and "không làm lại" in again.message


def test_errors_never_raise(env, monkeypatch):
    monkeypatch.setattr(pub, "_publish", lambda *a, **k: 1 / 0)
    res = _run(env)
    assert res.status == "failed" and "division by zero" in res.message


def test_probe_detects_stale_partial(tmp_path):
    target = tmp_path / "publish"
    cfg = {"stale_hours": 26}
    (target / "_manifest").mkdir(parents=True)
    pub._write_json_replace(target / "_manifest" / "latest.json",
                            {"updated_at": "2099-01-01T00:00:00+07:00"})
    ok = probe_publish(target, cfg, onedrive_running=lambda: True)
    assert ok.ok, ok.message
    assert not (target / "_manifest" / ".probe").exists()
    part = target / "parquet" / ".x.parquet.partial"
    part.parent.mkdir(parents=True)
    part.write_bytes(b"partial")
    old = time.time() - 3 * 3600
    os.utime(part, (old, old))
    bad = probe_publish(target, cfg, onedrive_running=lambda: True)
    assert not bad.ok and "partial" in bad.message


def test_probe_reports_onedrive_and_stale_latest(tmp_path):
    target = tmp_path / "publish"
    (target / "_manifest").mkdir(parents=True)
    pub._write_json_replace(target / "_manifest" / "latest.json",
                            {"updated_at": "2020-01-01T00:00:00+07:00"})
    res = probe_publish(target, {"stale_hours": 26}, onedrive_running=lambda: False)
    assert not res.ok
    assert "OneDrive.exe" in res.message and "latest.json" in res.message
    assert not probe_publish(None, {}).ok


def test_cli_exit_codes(env, monkeypatch, capsys):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "publish_cli", Path(__file__).resolve().parents[1] / "scripts" / "publish.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setenv("MONOCLE_DB_PATH", str(env["db"]))
    monkeypatch.setattr(pub, "DEFAULT_KEEP_REVIEW_DAYS", 7)
    assert cli.main(["--date", "2026-10-04"]) == 0
    assert "disabled" in capsys.readouterr().out
    assert cli.main(["--date", "2026-10-04", "--dry-run", "--target", str(env["target"])]) == 0
    assert not env["target"].exists()
    assert cli.main(["--date", "2026-10-04", "--target", str(env["target"])]) == 0
    assert (env["target"] / "_manifest" / "latest.json").exists()
    assert cli.main(["--date", "sai"]) == 1
