"""
Vòng 3 hạ tầng — DoD predicate + export/ingest (agent-agnostic, không LLM).
"""

from __future__ import annotations

import hashlib
import json

from src.agent.contract.dod import check_dod, verify_preconditions
from src.agent.ingest.runner import AgentRunner
from src.db.store import ArticleStore
from src.handoff.catalog import Catalog

CLEANED = "Alpha beta gamma đầu ngành. Delta epsilon zeta lao động giảm mạnh."


def _make_wp(tmp_path, article_id="art1", change_state="NEW"):
    raw = b"<html><body>raw bytes</body></html>"
    raw_path = tmp_path / f"{article_id}.html"
    raw_path.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    wp = {
        "schema_version": "1.0", "article_id": article_id,
        "source_url": "https://cafef.vn/x.chn", "domain": "cafef.vn",
        "raw_html_path": str(raw_path), "raw_sha256": sha,
        "cleaned_text": CLEANED, "capture_status": "ok", "change_state": change_state,
    }
    wp_path = tmp_path / f"{article_id}.pkg.json"
    wp_path.write_text(json.dumps(wp, ensure_ascii=False), encoding="utf-8")
    return wp, str(wp_path), sha


def _make_output(article_id="art1", confidence=0.78, quality="high", ncite=2):
    cites = [
        {"claim": "c1", "source_span": "Alpha beta gamma đầu ngành.", "source_offset": 0},
        {"claim": "c2", "source_span": "Delta epsilon zeta lao động giảm mạnh.", "source_offset": 28},
    ][:ncite]
    return {
        "output_schema_version": "1.0", "article_id": article_id,
        # abstractive/key_points/implication phải là chữ RIÊNG, không copy CLEANED
        # (predicate value_added + implication_specific).
        "summary": {"abstractive": "tóm tắt do agent tự viết",
                    "key_points": ["ý chắt lọc một", "ý chắt lọc hai"]},
        "implication": {"text": "Chi phí nhân sự giảm có thể nới biên lợi nhuận quý tới, "
                                "nhưng làm chậm mở rộng doanh thu.",
                        "impact_area": "market"},
        "materiality": {"score": 0.6, "time_sensitivity": "this_week"},
        "confidence": confidence,
        "citations": cites,
        "processing_metadata": {"agent_provider": "p", "model_used": "m",
                                "timestamp": "2026-08-17T09:00:00+07:00"},
        "extraction_quality": quality,
    }


# -- DoD predicate ----------------------------------------------------------
def test_dod_pass(tmp_path):
    wp, _, _ = _make_wp(tmp_path)
    ok, reasons = check_dod(_make_output(), wp)
    assert ok, reasons


def test_dod_ignores_low_confidence(tmp_path):
    # confidence do agent tự khai → KHÔNG còn là gate; thấp vẫn PASS nếu các predicate khác đạt
    wp, _, _ = _make_wp(tmp_path)
    ok, reasons = check_dod(_make_output(confidence=0.1), wp)
    assert ok, reasons


def test_dod_passes_without_confidence(tmp_path):
    # confidence là optional → thiếu hẳn vẫn PASS
    wp, _, _ = _make_wp(tmp_path)
    out = _make_output()
    del out["confidence"]
    ok, reasons = check_dod(out, wp)
    assert ok, reasons


def test_dod_ungrounded_citation(tmp_path):
    wp, _, _ = _make_wp(tmp_path)
    out = _make_output()
    out["citations"][1]["source_span"] = "chuỗi không có trong bài"
    ok, reasons = check_dod(out, wp)
    assert not ok
    assert any("grounded" in r for r in reasons)


def test_dod_too_few_citations(tmp_path):
    wp, _, _ = _make_wp(tmp_path)
    ok, reasons = check_dod(_make_output(ncite=1), wp)
    assert not ok
    assert any("citations" in r for r in reasons)


def test_dod_quality_low(tmp_path):
    wp, _, _ = _make_wp(tmp_path)
    ok, reasons = check_dod(_make_output(quality="low"), wp)
    assert not ok
    assert any("extraction_quality" in r for r in reasons)


# -- preconditions ----------------------------------------------------------
def test_precondition_integrity(tmp_path):
    wp, wp_path, _ = _make_wp(tmp_path)
    wp["raw_sha256"] = "deadbeef"
    ok, reasons = verify_preconditions(wp)
    assert not ok and any("integrity" in r for r in reasons)


def test_precondition_held_state(tmp_path):
    wp, _, _ = _make_wp(tmp_path, change_state="TEMPLATE_DRIFT")
    ok, reasons = verify_preconditions(wp, check_integrity=False)
    assert not ok and any("change_state" in r for r in reasons)


# -- export + ingest end-to-end --------------------------------------------
def _store(tmp_path):
    return ArticleStore(db_path=str(tmp_path / "t.db"))


def test_ingest_done(tmp_path):
    store = _store(tmp_path)
    wp, wp_path, sha = _make_wp(tmp_path)
    Catalog(store).enqueue(wp["article_id"], sha, "cafef.vn", wp_path, "NEW")

    runner = AgentRunner(store, task_dir=str(tmp_path / "tasks"))

    res = runner.ingest_output(_make_output())
    assert res["dod_pass"] is True
    assert store.get_agent_output("art1", sha)["dod_pass"] == 1
    assert Catalog(store).counts().get("done") == 1


def _make_lean_output(article_id="art1"):
    return {
        "article_id": article_id,
        "summary": "Tóm tắt phân tích do agent tự viết cho doanh nghiệp.",
        "key_points": ["Luận điểm kinh doanh số một", "Luận điểm thị trường số hai"],
        "implication": "Chi phí nhân sự giảm có thể nới biên lợi nhuận quý tới, nhưng làm chậm mở rộng doanh thu.",
        "sentiment": "positive",
        "time_sensitivity": "today",
        "citations": [
            "Alpha beta gamma đầu ngành.",
            "Delta epsilon zeta lao động giảm mạnh.",
        ],
    }


def test_dod_pass_lean_output(tmp_path):
    wp, _, _ = _make_wp(tmp_path)
    ok, reasons = check_dod(_make_lean_output(), wp)
    assert ok is True, reasons


def test_runner_ingest_lean_output_and_auto_metadata(tmp_path):
    store = _store(tmp_path)
    wp, wp_path, sha = _make_wp(tmp_path)
    Catalog(store).enqueue(wp["article_id"], sha, "cafef.vn", wp_path, "NEW")

    runner = AgentRunner(store, task_dir=str(tmp_path / "tasks"))

    res = runner.ingest_output(_make_lean_output())
    assert res["dod_pass"] is True
    out_rec = store.get_agent_output("art1", sha)
    assert out_rec["dod_pass"] == 1
    assert out_rec["agent_provider"] == "antigravity"
    assert out_rec["model_used"] == "flash"
    assert Catalog(store).counts().get("done") == 1


def test_ingest_fail_marks_failed(tmp_path):
    store = _store(tmp_path)
    wp, wp_path, sha = _make_wp(tmp_path)
    Catalog(store).enqueue(wp["article_id"], sha, "cafef.vn", wp_path, "NEW")
    runner = AgentRunner(store, task_dir=str(tmp_path / "tasks"))

    res = runner.ingest_output(_make_output(quality="low"))   # extraction_quality=low → DoD fail
    assert res["dod_pass"] is False
    assert Catalog(store).counts().get("failed") == 1


def test_ingest_idempotent_replay(tmp_path):
    store = _store(tmp_path)
    wp, wp_path, sha = _make_wp(tmp_path)
    Catalog(store).enqueue(wp["article_id"], sha, "cafef.vn", wp_path, "NEW")
    runner = AgentRunner(store, task_dir=str(tmp_path / "tasks"))
    runner.ingest_output(_make_output())
    again = runner.ingest_output(_make_output())
    assert again.get("cached") is True and again["dod_pass"] is True


def test_runner_ingest_upgrades_legacy_work_package(tmp_path):
    """Gói 1.0 cũ có raw_sha256 lệch đĩa phải tự nâng cấp sang bản 1.1 để nạp thành công."""
    store = _store(tmp_path)
    wp, wp_path, sha = _make_wp(tmp_path, article_id="art_legacy")
    # Giả lập raw_html bị thay đổi trên đĩa khiến raw_sha256 trong gói cũ bị lệch
    wp["raw_sha256"] = "outdated_sha_from_old_scrape"
    with open(wp_path, "w", encoding="utf-8") as f:
        json.dump(wp, f)

    Catalog(store).enqueue("art_legacy", "outdated_sha_from_old_scrape", "cafef.vn", wp_path, "NEW")
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO articles (url_title_hash, url, title, source_domain, content_text, published_at, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("art_legacy", "https://cafef.vn/x.chn", "Tin cu", "cafef.vn", CLEANED, "2026-09-21T10:00:00+07:00", "2026-09-21T10:05:00+07:00")
        )
        conn.commit()

    runner = AgentRunner(store, task_dir=str(tmp_path / "tasks"))
    out = _make_output(article_id="art_legacy")
    res = runner.ingest_output(out)
    assert res["dod_pass"] is True
    assert res["ok"] is True
