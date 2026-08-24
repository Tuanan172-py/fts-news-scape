"""
test_dynamic_entities.py — Unit tests kiểm thử hệ thống Entity động đa tầng:
  1. Khớp từ ngắn được bảo vệ (PROTECTED_SHORT_WORDS: Quỹ, Mỹ, Fed, Vàng...).
  2. Khớp cụm từ alias mở rộng của ngành (vd QUY -> "Quỹ đầu tư mạo hiểm").
  3. Chống false-positive qua Word Boundary Regex.
  4. Đăng ký & Compile các nhóm mới: macro, assets, institutions.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.agent.entities import EntityRegistry, load_registry
from src.agent.l1_classifier import classify_title
from src.users.compile import compile_user, write_user_xlsx


@pytest.fixture(scope="module")
def registry():
    return load_registry()


def test_quy_industry_alias_matching(registry: EntityRegistry):
    """Kiểm tra mã QUY bắt đúng cụm từ 'Quỹ đầu tư mạo hiểm'."""
    title = "Quỹ đầu tư mạo hiểm 500 tỷ rót vốn vào startup công nghệ"
    res = classify_title(title, registry)
    
    # Phải nhận diện được thực thể
    matched_ids = res["entity_ids"]
    assert any("QUY" in eid for eid in matched_ids), f"Không tìm thấy QUY trong {matched_ids}"
    assert res["relevance"] == "industry"
    assert not res["needs_agent"]


def test_protected_short_words_matching(registry: EntityRegistry):
    """Kiểm tra các từ ngắn được bảo vệ: Mỹ, Vàng, Fed, Trái phiếu."""
    # 1. Mỹ
    res_my = classify_title("Mỹ chuẩn bị công bố gói thuế quan mới", registry)
    assert any("MY" in eid for eid in res_my["entity_ids"])

    # 2. Vàng & Trái phiếu
    res_asset = classify_title("Giá vàng trong nước biến động khi thị trường trái phiếu sôi động", registry)
    asset_ids = res_asset["entity_ids"]
    assert any("VANG" in eid for eid in asset_ids)
    assert any("TRAI_PHIEU" in eid for eid in asset_ids)


def test_prevent_false_positive_substrings(registry: EntityRegistry):
    """Kiểm tra không bị false positive khi từ ngắn nằm trong từ khác."""
    # 'quyết định' không được kích hoạt 'quy'
    res = classify_title("Hội đồng quản trị quyết định phương án kinh doanh", registry)
    assert not any(eid.startswith("IND_") and "QUY" in eid for eid in res["entity_ids"])


def test_user_subscription_selection_with_new_categories(registry: EntityRegistry):
    """Kiểm tra User đăng ký các nhóm mới: macro, assets, institutions, industries."""
    doc = {
        "industries": ["QUY", "THEP"],
        "macro": ["MY", "TRUNG_QUOC", "LAI_SUAT"],
        "nations": ["HAN_QUOC", "NGA", "EU"],
        "themes": ["DAU_TU_CONG", "FDI", "TIN_DUNG", "TY_GIA"],
        "assets": ["TRAI_PHIEU", "VANG", "TIEN_MA_HOA", "HANG_HOA_NONG_SAN"],
        "institutions": ["NHNN", "FED", "BO_TAI_CHINH", "WB_IMF"],
    }
    ids, unknown = registry.select(doc)
    assert not unknown, f"Có unknown entities: {unknown}"
    
    # Kiểm tra các ID được map đầy đủ
    assert any("IND_" in eid and "QUY" in eid for eid in ids)
    assert any("IND_" in eid and "THEP" in eid for eid in ids)
    assert "MACRO_GEO:MY" in ids
    assert "MACRO_GEO:TRUNG_QUOC" in ids
    assert "MACRO_GEO:HAN_QUOC" in ids
    assert "MACRO_GEO:NGA" in ids
    assert "MACRO_THEME:LAI_SUAT" in ids
    assert "MACRO_THEME:DAU_TU_CONG" in ids
    assert "MACRO_THEME:FDI" in ids
    assert "ASSET_CLASS:TRAI_PHIEU" in ids
    assert "ASSET_CLASS:VANG" in ids
    assert "ASSET_CLASS:TIEN_MA_HOA" in ids
    assert "INSTITUTION:NHNN" in ids
    assert "INSTITUTION:FED" in ids
    assert "INSTITUTION:BO_TAI_CHINH" in ids
    assert "INSTITUTION:WB_IMF" in ids


def test_compile_user_with_new_groups(registry: EntityRegistry):
    """Kiểm tra compile file Excel của user có các cột mới sang YAML config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        xlsx_path = tmp_path / "entities.xlsx"
        doc = {
            "tickers": ["HPG"],
            "industries": ["QUY"],
            "nations": ["MY", "HAN_QUOC"],
            "themes": ["DAU_TU_CONG"],
            "assets": ["TRAI_PHIEU"],
            "institutions": ["NHNN", "BO_TAI_CHINH"],
        }
        write_user_xlsx(xlsx_path, doc, {"user": "TestUser"})
        
        cfg_dir = tmp_path / "cfg"
        res = compile_user("TestUser", xlsx_path, registry, users_config_dir=cfg_dir, input_dir=tmp_path)
        
        assert res["name"] == "TestUser"
        assert len(res["unknown"]) == 0
        assert "TICKER:HPG" in res["ids"]
        assert "MACRO_GEO:MY" in res["ids"]
        assert "MACRO_GEO:HAN_QUOC" in res["ids"]
        assert "MACRO_THEME:DAU_TU_CONG" in res["ids"]
        assert "ASSET_CLASS:TRAI_PHIEU" in res["ids"]
        assert "INSTITUTION:NHNN" in res["ids"]
        assert "INSTITUTION:BO_TAI_CHINH" in res["ids"]
        assert any("QUY" in eid for eid in res["ids"])

