"""
Test cổng check_l1_dod của bản ghi nhận diện thực thể.
Registry dựng tay; DoD dùng schema thật l1-entity-output-v1 (contract_validator).
"""
from __future__ import annotations

from src.agent.l1_router import check_l1_dod

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
