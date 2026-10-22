"""
Test L1Runner với DB tạm: ingest_output (đạt/không đạt DoD) → l1_outputs + status done/failed; idempotent.
"""
from __future__ import annotations

import pytest

from src.agent.catalog.entities import EntityRegistry
from src.agent.ingest.l1_runner import L1Runner
from src.db.store import ArticleStore

ENTITIES = [
    {"entity_id": "TICKER:HPG", "type": "TICKER", "code": "HPG",
     "canonical_name": "CTCP Tập đoàn Hòa Phát", "aliases": ["CTCP Tập đoàn Hòa Phát", "Hòa Phát"],
     "attributes": {"gics1": "Nguyên vật liệu"}, "sources": []},
]


@pytest.fixture
def runner(tmp_path):
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    reg = EntityRegistry(ENTITIES, {})
    return L1Runner(store, reg, task_dir=str(tmp_path / "l1"))


def _output(aid, title, ok=True):
    o = {
        "l1_output_version": "1.0", "article_id": aid, "title": title,
        "recognized": True,
        "entities": [{"surface": "Hòa Phát", "entity_id": "TICKER:HPG",
                      "type": "TICKER", "method": "alias", "in_list": True, "confidence": 0.9}],
        "categories": {"ticker_company": "done", "etf_fund": "none", "index": "none",
                       "exchange": "none", "industry_sector": "none"},
        "citations": [{"source_span": title}],
        "confidence": 0.9,
        "processing_metadata": {"agent_provider": "x", "model_used": "m", "timestamp": "t"},
    }
    if not ok:
        o["citations"] = [{"source_span": "chuỗi không nằm trong tiêu đề"}]  # ungrounded -> DoD fail
    return o


def _task(runner, aid, title):
    runner.store.upsert_l1_task({"article_id": aid, "domain": "cafef.vn", "title": title,
                                 "code_first_json": None, "route": "article_lane",
                                 "packet_path": None, "enqueued_at": "2026-10-22T09:00:00+07:00"})


def test_ingest_pass_marks_done(runner):
    title = "Hòa Phát báo lãi quý 2 tăng mạnh"
    _task(runner, "a3", title)
    res = runner.ingest_output(_output("a3", title, ok=True))
    assert res["dod_pass"] is True
    assert runner.store.get_l1_task("a3")["status"] == "done"
    assert runner.store.get_l1_output("a3")["dod_pass"] == 1


def test_ingest_fail_marks_failed(runner):
    title = "Hòa Phát báo lãi quý 2 tăng mạnh"
    _task(runner, "a4", title)
    res = runner.ingest_output(_output("a4", title, ok=False))
    assert res["dod_pass"] is False
    assert runner.store.get_l1_task("a4")["status"] == "failed"


def test_ingest_idempotent_replay(runner):
    title = "Hòa Phát báo lãi quý 2 tăng mạnh"
    _task(runner, "a5", title)
    runner.ingest_output(_output("a5", title, ok=True))
    again = runner.ingest_output(_output("a5", title, ok=True))
    assert again.get("cached") is True and again["dod_pass"] is True


def test_ingest_without_task(runner):
    assert runner.ingest_output(_output("nope", "x"))["ok"] is False
