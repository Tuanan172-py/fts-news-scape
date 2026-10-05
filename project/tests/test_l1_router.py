"""
Test quy trình L1 2 tầng: route (code-first split) + build packet + check_l1_dod.
Registry dựng tay; DoD dùng schema thật l1-entity-output-v1 (contract_validator).
"""
from __future__ import annotations

import pytest

from src.agent.entities import EntityRegistry
from src.agent.l1_router import build_l1_task_packet, check_l1_dod, route_article

ENTITIES = [
    {"entity_id": "TICKER:HPG", "type": "TICKER", "code": "HPG",
     "canonical_name": "CTCP Tập đoàn Hòa Phát", "aliases": ["CTCP Tập đoàn Hòa Phát", "Hòa Phát"],
     "attributes": {"gics1": "Nguyên vật liệu"}, "sources": []},
]


@pytest.fixture
def reg():
    return EntityRegistry(ENTITIES, {})


def _valid_output(title):
    return {
        "l1_output_version": "1.0", "article_id": "a1", "title": title,
        "recognized": True,
        "entities": [{"surface": "Hòa Phát", "entity_id": "TICKER:HPG",
                      "type": "TICKER", "method": "alias", "in_list": True, "confidence": 0.9}],
        "categories": {"ticker_company": "done", "etf_fund": "none", "index": "none",
                       "exchange": "none", "industry_sector": "none"},
        "citations": [{"source_span": title}],
        "confidence": 0.9,
        "processing_metadata": {"agent_provider": "x", "model_used": "m", "timestamp": "t"},
    }


def test_route_resolved(reg):
    art = {"article_id": "a1", "structure": {"headings": [{"level": 1, "text": "Hòa Phát báo lãi"}]}}
    assert route_article(art, reg)["route"] == "resolved"


def test_route_needs_agent_and_packet(reg):
    art = {"article_id": "a2", "domain": "cafef.vn",
           "structure": {"headings": [{"level": 1, "text": "Thị trường hàng hoá thế giới biến động"}]}}
    rec = route_article(art, reg)
    assert rec["route"] == "needs_agent"
    pkt = build_l1_task_packet(art, rec)
    assert pkt["layer"] == "L1_ENTITY_RECOGNITION"
    assert pkt["input"]["title"] == "Thị trường hàng hoá thế giới biến động"
    assert pkt["output_contract"]["schema_name"] == "l1-entity-output-v1"
    assert pkt["instructions_ref"].endswith("l1-entity-instructions-v1.md")


def test_dod_pass():
    title = "Hòa Phát báo lãi quý 2"
    ok, reasons = check_l1_dod(_valid_output(title), title)
    assert ok, reasons


def test_dod_fail_surface_not_in_title():
    title = "Tin thị trường chung"
    out = _valid_output(title)  # surface 'Hòa Phát' không có trong title này
    ok, reasons = check_l1_dod(out, title)
    assert not ok and any("surface" in r for r in reasons)


def test_dod_fail_category_done_without_entity():
    title = "Không có gì"
    out = _valid_output(title)
    out["recognized"] = False
    out["entities"] = []
    out["citations"] = []
    # vẫn để category done -> phải bị bắt lỗi
    ok, reasons = check_l1_dod(out, title)
    assert not ok
