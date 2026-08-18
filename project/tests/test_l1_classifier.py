"""
Test LỚP 1 — phân loại tin theo entity qua tiêu đề (không LLM).
Dùng registry dựng tay để độc lập với data/entities.
"""
from __future__ import annotations

import pytest

from src.agent.entities import EntityRegistry
from src.agent.l1_classifier import classify_article, classify_title, title_of

ENTITIES = [
    {"entity_id": "TICKER:HPG", "type": "TICKER", "code": "HPG",
     "canonical_name": "CTCP Tập đoàn Hòa Phát", "aliases": ["CTCP Tập đoàn Hòa Phát", "Hòa Phát"],
     "attributes": {"gics1": "Nguyên vật liệu", "gics3": "Thép"}, "sources": []},
    {"entity_id": "TICKER:VCB", "type": "TICKER", "code": "VCB",
     "canonical_name": "Ngân hàng TMCP Ngoại thương Việt Nam",
     "aliases": ["Ngân hàng TMCP Ngoại thương Việt Nam", "Ngoại thương Việt Nam"],
     "attributes": {"gics1": "Tài chính", "gics2": "Ngân hàng"}, "sources": []},
    {"entity_id": "INDEX:VNINDEX", "type": "INDEX", "code": "VNINDEX",
     "canonical_name": "VN-Index", "aliases": ["VN-Index", "VNINDEX"],
     "attributes": {"exchange": "HOSE"}, "sources": []},
    {"entity_id": "SECTOR_FPA:THEP", "type": "SECTOR_FPA", "code": "Thep",
     "canonical_name": "Thép", "aliases": ["Thép", "Thep"], "attributes": {}, "sources": []},
]
GROUPS = {
    "co_ban": {"include_types": ["TICKER"]},
    "fta": {"include_types": ["INDEX", "SECTOR_FPA"]},
    "watch": {"include_entities": ["TICKER:HPG"]},
}


@pytest.fixture
def reg():
    return EntityRegistry(ENTITIES, GROUPS)


def test_title_of_from_headings():
    art = {"structure": {"headings": [{"level": 2, "text": "x"}, {"level": 1, "text": "Tiêu đề chính"}]}}
    assert title_of(art) == "Tiêu đề chính"


def test_title_of_fallback_cleaned_text():
    assert title_of({"cleaned_text": "Dòng đầu\nphần thân"}) == "Dòng đầu"


def test_classify_security_and_infer_industry(reg):
    r = classify_title("Hòa Phát báo lãi quý 2 tăng mạnh", reg)
    assert "TICKER:HPG" in r["entity_ids"]
    assert r["relevance"] == "entity"
    assert r["primary_entity"] == "TICKER:HPG"
    # ngành suy ra từ GICS của HPG dù title không có chữ 'Thép'
    assert "Thép" in r["industries"] and "Nguyên vật liệu" in r["industries"]


def test_relevance_market_only(reg):
    r = classify_title("VN-Index vượt 1.300 điểm", reg)
    assert r["relevance"] == "market"
    assert r["entity_types"] == ["INDEX"]
    assert r["needs_agent"] is False


def test_relevance_none_needs_agent(reg):
    r = classify_title("Thời tiết Hà Nội cuối tuần", reg)
    assert r["relevance"] == "none" and r["entity_ids"] == []
    # code-first không khớp -> chuyển handoff cho agent L1
    assert r["needs_agent"] is True


def test_classify_article_attaches_ids(reg):
    art = {"article_id": "a1", "domain": "cafef.vn",
           "structure": {"headings": [{"level": 1, "text": "VCB dẫn dắt nhóm ngân hàng"}]}}
    r = classify_article(art, reg)
    assert r["article_id"] == "a1" and r["domain"] == "cafef.vn"
    assert "TICKER:VCB" in r["entity_ids"]
    assert "Ngân hàng" in r["industries"]
