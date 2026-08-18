"""
Test EntityRegistry — đăng ký theo người dùng (select/subscribers_for) + nhận diện text.
Dùng registry nhỏ dựng tay để không phụ thuộc data/entities/entities.json.
"""
from __future__ import annotations

import pytest

from src.agent.entities import EntityRegistry, _user_enabled

ENTITIES = [
    {"entity_id": "TICKER:HPG", "type": "TICKER", "code": "HPG",
     "canonical_name": "CTCP Tập đoàn Hòa Phát",
     "aliases": ["CTCP Tập đoàn Hòa Phát", "Hòa Phát"],
     "attributes": {"gics1": "Nguyên vật liệu"}, "sources": []},
    {"entity_id": "TICKER:VCB", "type": "TICKER", "code": "VCB",
     "canonical_name": "Ngân hàng TMCP Ngoại thương Việt Nam",
     "aliases": ["Ngân hàng TMCP Ngoại thương Việt Nam", "Ngoại thương Việt Nam", "Vietcombank"],
     "attributes": {"gics1": "Tài chính"}, "sources": []},
    {"entity_id": "INDEX:VNINDEX", "type": "INDEX", "code": "VNINDEX",
     "canonical_name": "VN-Index", "aliases": ["VN-Index", "VNINDEX"],
     "attributes": {"exchange": "HOSE"}, "sources": []},
    {"entity_id": "IND_GICS3:THEP", "type": "INDUSTRY_GICS3", "code": "THEP",
     "canonical_name": "Thép", "aliases": ["Thép"], "attributes": {"parent": "x"}, "sources": []},
]


@pytest.fixture
def reg():
    return EntityRegistry(ENTITIES)


# ---- select: ánh xạ file đăng ký (liệt kê theo nhóm) -> entity_id ----------
def test_select_tickers_and_index(reg):
    ids, unknown = reg.select({"tickers": ["HPG", "VCB"], "indices": ["VNINDEX"]})
    assert ids == {"TICKER:HPG", "TICKER:VCB", "INDEX:VNINDEX"} and unknown == []


def test_select_industry_by_code(reg):
    ids, unknown = reg.select({"industries": ["THEP"]})   # chuẩn: dùng code ngành
    assert ids == {"IND_GICS3:THEP"} and unknown == []


def test_select_industry_code_case_insensitive(reg):
    ids, unknown = reg.select({"industries": ["thep"]})   # code viết thường vẫn khớp
    assert ids == {"IND_GICS3:THEP"} and unknown == []


def test_select_industry_by_name_rejected(reg):
    # đồng bộ: industries CHỈ nhận code, tên ngành bị coi là unknown (không còn fallback theo tên)
    ids, unknown = reg.select({"industries": ["Thép"]})
    assert ids == set() and ("industries", "Thép") in unknown


def test_select_unknown_reported(reg):
    ids, unknown = reg.select({"tickers": ["ZZZ"], "industries": ["Không Có"]})
    assert ids == set()
    assert ("tickers", "ZZZ") in unknown and ("industries", "Không Có") in unknown


# ---- subscribers_for: người dùng nào chạm tới entity của tin ---------------
def test_subscribers_for():
    subs = {
        "AnPT": {"TICKER:HPG", "INDEX:VNINDEX"},
        "A": {"TICKER:VCB"},
    }
    reg = EntityRegistry(ENTITIES, subs)
    assert reg.subscribers_for(["TICKER:HPG"]) == {"AnPT"}
    assert reg.subscribers_for(["TICKER:VCB", "INDEX:VNINDEX"]) == {"A", "AnPT"}
    assert reg.subscribers_for(["IND_GICS3:THEP"]) == set()


def test_resolve_subscription_filters_invalid():
    reg = EntityRegistry(ENTITIES, {"X": {"TICKER:HPG", "TICKER:NOPE"}})
    assert reg.resolve_subscription("X") == {"TICKER:HPG"}


# ---- manifest: công tắc DEV bật/tắt từng người dùng ------------------------
def test_manifest_per_user_toggle():
    man = {"enabled": True, "default": False, "users": {"AnPT": True, "B": False}}
    assert _user_enabled(man, "AnPT") is True      # bật rõ ràng
    assert _user_enabled(man, "B") is False        # tắt rõ ràng
    assert _user_enabled(man, "C") is False        # chưa liệt kê -> theo default (False)


def test_manifest_global_off_overrides():
    man = {"enabled": False, "default": True, "users": {"AnPT": True}}
    assert _user_enabled(man, "AnPT") is False      # enabled=False tắt tất
    assert _user_enabled(man, "X") is False


# ---- nhận diện text --------------------------------------------------------
def test_match_by_code(reg):
    ids = [e["entity_id"] for e in reg.match("Cổ phiếu HPG tăng trần, VCB dẫn dắt")]
    assert "TICKER:HPG" in ids and "TICKER:VCB" in ids


def test_match_by_alias_diacritic_insensitive(reg):
    ids = [e["entity_id"] for e in reg.match("Tập đoàn Hoa Phat báo lãi")]  # thiếu dấu
    assert "TICKER:HPG" in ids
