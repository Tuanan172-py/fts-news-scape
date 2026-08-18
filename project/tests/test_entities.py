"""
Test EntityRegistry — resolve nhóm + nhận diện thực thể trong text (không LLM).
Dùng registry nhỏ dựng tay để không phụ thuộc data/entities/entities.json.
"""
from __future__ import annotations

import pytest

from src.agent.entities import EntityRegistry

ENTITIES = [
    {"entity_id": "TICKER:HPG", "type": "TICKER", "code": "HPG",
     "canonical_name": "CTCP Tập đoàn Hòa Phát",
     "aliases": ["CTCP Tập đoàn Hòa Phát", "Hòa Phát"],
     "attributes": {"gics1": "Nguyên vật liệu"}, "sources": []},
    {"entity_id": "TICKER:VCB", "type": "TICKER", "code": "VCB",
     "canonical_name": "Ngân hàng TMCP Ngoại thương Việt Nam",
     "aliases": ["Ngân hàng TMCP Ngoại thương Việt Nam", "Ngoại thương Việt Nam"],
     "attributes": {"gics1": "Tài chính"}, "sources": []},
    {"entity_id": "INDEX:VNINDEX", "type": "INDEX", "code": "VNINDEX",
     "canonical_name": "VN-Index", "aliases": ["VN-Index", "VNINDEX"],
     "attributes": {"exchange": "HOSE"}, "sources": []},
    {"entity_id": "SECTOR_FPA:THEP", "type": "SECTOR_FPA", "code": "Thep",
     "canonical_name": "Thép", "aliases": ["Thép", "Thep"],
     "attributes": {}, "sources": []},
]

GROUPS = {
    "co_ban": {"include_types": ["TICKER"]},
    "fta": {"include_types": ["INDEX", "SECTOR_FPA"], "include_gics1": ["Tài chính"]},
    "watch": {"include_entities": ["TICKER:HPG"]},
}


@pytest.fixture
def reg():
    return EntityRegistry(ENTITIES, GROUPS)


def test_unique_ids_and_lookup(reg):
    assert reg.get("TICKER:HPG")["code"] == "HPG"
    assert len(reg.entities) == 4


def test_resolve_group_by_type(reg):
    assert reg.resolve_group("co_ban") == {"TICKER:HPG", "TICKER:VCB"}


def test_resolve_group_union_gics1(reg):
    # INDEX + SECTOR_FPA + mọi TICKER ngành Tài chính (VCB)
    assert reg.resolve_group("fta") == {"INDEX:VNINDEX", "SECTOR_FPA:THEP", "TICKER:VCB"}


def test_resolve_group_explicit_entity(reg):
    assert reg.resolve_group("watch") == {"TICKER:HPG"}


def test_match_by_code(reg):
    ids = [e["entity_id"] for e in reg.match("Cổ phiếu HPG tăng trần, VCB dẫn dắt")]
    assert "TICKER:HPG" in ids and "TICKER:VCB" in ids


def test_match_by_alias_diacritic_insensitive(reg):
    ids = [e["entity_id"] for e in reg.match("Tập đoàn Hoa Phat báo lãi")]  # thiếu dấu
    assert "TICKER:HPG" in ids


def test_match_filtered_by_group(reg):
    txt = "HPG và VN-Index cùng tăng, nhóm Thép hút tiền"
    only_companies = [e["entity_id"] for e in reg.match(txt, group="co_ban")]
    assert only_companies == ["TICKER:HPG"]


def test_match_index_and_sector(reg):
    ids = [e["entity_id"] for e in reg.match("VN-Index vượt đỉnh, ngành Thép khởi sắc")]
    assert "INDEX:VNINDEX" in ids and "SECTOR_FPA:THEP" in ids
