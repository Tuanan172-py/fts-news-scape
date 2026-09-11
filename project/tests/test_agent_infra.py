"""
Vòng 3 hạ tầng — DoD predicate + export/ingest (agent-agnostic, không LLM).
"""

from __future__ import annotations

import hashlib
import json

from src.agent.dod import check_dod, verify_preconditions
from src.agent.runner import AgentRunner
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


def test_export_then_ingest_done(tmp_path):
    store = _store(tmp_path)
    wp, wp_path, sha = _make_wp(tmp_path)
    Catalog(store).enqueue(wp["article_id"], sha, "cafef.vn", wp_path, "NEW")

    runner = AgentRunner(store, task_dir=str(tmp_path / "tasks"))
    exported = runner.export_tasks(limit=10, require_l1=False, subscriber_only=False)
    assert len(exported) == 1
    packet = json.loads(open(exported[0]["path"], encoding="utf-8").read())
    assert packet["input"]["article_id"] == "art1"
    assert packet["output_contract"]["schema_name"] == "agent-output-v1"

    res = runner.ingest_output(_make_output())
    assert res["dod_pass"] is True
    assert store.get_agent_output("art1", sha)["dod_pass"] == 1
    assert Catalog(store).counts().get("done") == 1


def test_ingest_fail_marks_failed(tmp_path):
    store = _store(tmp_path)
    wp, wp_path, sha = _make_wp(tmp_path)
    Catalog(store).enqueue(wp["article_id"], sha, "cafef.vn", wp_path, "NEW")
    runner = AgentRunner(store, task_dir=str(tmp_path / "tasks"))
    runner.export_tasks(limit=10, require_l1=False)

    res = runner.ingest_output(_make_output(quality="low"))   # extraction_quality=low → DoD fail
    assert res["dod_pass"] is False
    assert Catalog(store).counts().get("failed") == 1


def test_ingest_idempotent_replay(tmp_path):
    store = _store(tmp_path)
    wp, wp_path, sha = _make_wp(tmp_path)
    Catalog(store).enqueue(wp["article_id"], sha, "cafef.vn", wp_path, "NEW")
    runner = AgentRunner(store, task_dir=str(tmp_path / "tasks"))
    runner.export_tasks(limit=10, require_l1=False)
    runner.ingest_output(_make_output())
    again = runner.ingest_output(_make_output())
    assert again.get("cached") is True and again["dod_pass"] is True


# -- Ordering L1 → Gold (rule 05 §2.5) --------------------------------------
def _seed_l1_pass(store, article_id, entity_ids):
    """Ghi 1 l1_outputs đạt DoD theo đúng schema l1-entity-output-v1 (key `entity_id`)."""
    out = {
        "l1_output_version": "1.0", "article_id": article_id, "title": "t",
        "recognized": True,
        "entities": [{"surface": "t", "entity_id": e, "type": "TICKER",
                      "method": "alias", "in_list": True} for e in entity_ids],
        "categories": {"ticker_company": "done"},
        "citations": [{"source_span": "t"}],
        "processing_metadata": {"agent_provider": "p", "model_used": "m", "timestamp": "t"},
    }
    store.insert_l1_output({
        "article_id": article_id, "output_json": json.dumps(out, ensure_ascii=False),
        "recognized": 1, "agent_provider": "p", "model_used": "m", "confidence": 0.9,
        "dod_pass": 1, "dod_reasons": "[]", "created_at": "t"})


def test_export_requires_l1_by_default(tmp_path):
    """Chưa có L1 → không bốc việc (khỏi đốt token Gold cho bài không định tuyến được)."""
    store = _store(tmp_path)
    wp, wp_path, sha = _make_wp(tmp_path)
    Catalog(store).enqueue(wp["article_id"], sha, "cafef.vn", wp_path, "NEW")
    runner = AgentRunner(store, task_dir=str(tmp_path / "tasks"))

    assert runner.export_tasks(limit=10) == []
    assert Catalog(store).counts().get("pending") == 1      # việc vẫn còn nguyên, chưa bị claim

    _seed_l1_pass(store, "art1", ["TICKER:HPG"])
    assert len(runner.export_tasks(limit=10)) == 1


def test_export_embeds_l1_entity_ids(tmp_path):
    """Packet Gold phải nhúng entity_id từ l1_outputs (schema L1 KHÔNG có key `code`)."""
    store = _store(tmp_path)
    wp, wp_path, sha = _make_wp(tmp_path)
    Catalog(store).enqueue(wp["article_id"], sha, "cafef.vn", wp_path, "NEW")
    _seed_l1_pass(store, "art1", ["TICKER:HPG", "TICKER:VCB"])

    runner = AgentRunner(store, task_dir=str(tmp_path / "tasks"))
    exported = runner.export_tasks(limit=10)
    assert exported[0]["l1_entities"] == ["TICKER:HPG", "TICKER:VCB"]
    packet = json.loads(open(exported[0]["path"], encoding="utf-8").read())
    assert packet["input"]["l1_entities"] == ["TICKER:HPG", "TICKER:VCB"]
