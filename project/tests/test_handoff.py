"""
Tests handoff (phase-03): silver build, contract validator, catalog idempotency/claim, e2e process.
"""

import hashlib
import json
from pathlib import Path

import pytest

from src.core.models import Article
from src.db.store import ArticleStore
from src.handoff.catalog import Catalog
from src.handoff.contract_validator import validate
from src.handoff.work_package import WorkPackageBuilder
from src.pipeline.run import process_meta
from src.pipeline.silver_builder import SilverBuilder

_HTML = ("<html><body><div id='mainContent'><h1>Tiêu đề</h1>"
         + "<p>Nội dung bài viết đủ dài để bóc tách. </p>" * 20
         + "</div></body></html>")


@pytest.fixture
def bronze(tmp_path):
    body = _HTML.encode("utf-8")
    sha = hashlib.sha256(body).hexdigest()
    hash_ = "h" + sha[:63]
    d = tmp_path / "data" / "raw_html" / "example.vn" / "20260813"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{hash_}.html").write_bytes(body)
    meta = {"source_url": "https://example.vn/a.html", "url_title_hash": hash_,
            "fetch_ts": "2026-08-13T10:00:00+07:00", "render_method": "requests",
            "html_path": str(d / f"{hash_}.html"), "content_sha256": sha,
            "encoding": "utf-8", "images": [], "capture_status": "ok", "missing": []}
    (d / f"{hash_}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return {"meta_path": str(d / f"{hash_}.meta.json"), "meta": meta, "hash": hash_, "sha": sha}


def test_silver_deterministic(bronze):
    b = SilverBuilder()
    raw = Path(bronze["meta"]["html_path"]).read_bytes()
    s1 = b.build(bronze["meta"], raw)
    s2 = b.build(bronze["meta"], raw)
    assert s1 == s2                                  # deterministic
    assert s1["cleaned_text"] and s1["content_sha256"] == bronze["sha"]
    assert s1["domain"] == "example.vn"


def test_work_package_valid(bronze):
    raw = Path(bronze["meta"]["html_path"]).read_bytes()
    silver = SilverBuilder().build(bronze["meta"], raw)
    pkg = WorkPackageBuilder().build(silver, bronze["meta"], "NEW", published_at="2026-08-13T10:00:00+07:00")
    ok, errors = validate(pkg, "work-package-v1")
    assert ok, errors
    assert pkg["raw_sha256"] == bronze["sha"] and "raw_html_path" in pkg
    assert "cleaned_text" in pkg and pkg["change_state"] == "NEW"


def test_validator_rejects_missing_field():
    ok, errors = validate({"schema_version": "1.0"}, "work-package-v1")
    assert not ok and any("article_id" in e for e in errors)


def test_process_meta_e2e_and_catalog(tmp_path, bronze):
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    store.insert(Article(url="https://example.vn/a.html", title="Tiêu đề",
                         source_domain="example.vn", published_at="2026-08-13T10:00:00+07:00"))
    res = process_meta(store, bronze["meta_path"],
                       silver_dir=str(tmp_path / "silver"),
                       package_dir=str(tmp_path / "pkg"))
    assert res["ok"] and res["state"] == "NEW" and res["enqueue_status"] == "pending"
    assert Path(res["silver_path"]).exists() and Path(res["package_path"]).exists()

    cat = Catalog(store)
    # idempotent enqueue: chạy lại process → cùng (article_id, raw_sha256) không nhân đôi
    process_meta(store, bronze["meta_path"], silver_dir=str(tmp_path / "silver"),
                 package_dir=str(tmp_path / "pkg"))
    assert sum(cat.counts().values()) == 1

    claimed = cat.claim("w1")
    assert claimed and claimed["article_id"] == bronze["hash"]
    assert cat.claim("w2") is None                    # không double-claim
    cat.mark_done(claimed["id"])
    assert cat.counts().get("done") == 1


def test_unchanged_second_capture(tmp_path, bronze):
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    r1 = process_meta(store, bronze["meta_path"], silver_dir=str(tmp_path / "s"),
                      package_dir=str(tmp_path / "p"))
    r2 = process_meta(store, bronze["meta_path"], silver_dir=str(tmp_path / "s"),
                      package_dir=str(tmp_path / "p"))
    assert r1["state"] == "NEW" and r2["state"] == "UNCHANGED"


def test_agent_output_sample_valid():
    sample = json.loads((Path(__file__).resolve().parent.parent / "schemas" / "samples"
                         / "agent-output-sample.json").read_text(encoding="utf-8"))
    ok, errors = validate(sample, "agent-output-v1")
    assert ok, errors
