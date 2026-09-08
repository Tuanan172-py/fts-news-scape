"""P1 — compile xlsx → yaml, báo unknown, manifest bật/tắt."""
from __future__ import annotations

import _userkit as k
import yaml

from src.users.compile import (
    compile_all, compile_user, enabled_users, read_user_csv, read_user_xlsx,
    write_user_csv, write_user_xlsx,
)


def test_roundtrip_xlsx(tmp_path):
    p = tmp_path / "entities.xlsx"
    write_user_xlsx(p, {"tickers": ["HPG", "FPT"], "industries": ["thep"]}, {"user": "AnPT"})
    doc, meta = read_user_xlsx(p)
    # industries dùng CODE → chuẩn hoá viết hoa như các nhóm mã khác
    assert doc["tickers"] == ["HPG", "FPT"] and doc["industries"] == ["THEP"]
    assert meta["user"] == "AnPT"


def test_read_xlsx_single_sheet_without_meta(tmp_path):
    """User chỉ nhập duy nhất 1 sheet, không có sheet meta, username suy từ tên file."""
    p = tmp_path / "AnPT_news.xlsx"
    write_user_xlsx(p, {"tickers": ["HPG", "VCB"], "themes": ["LAI_SUAT"]})  # không truyền meta
    doc, meta = read_user_xlsx(p)
    assert doc["tickers"] == ["HPG", "VCB"]
    assert doc["themes"] == ["LAI_SUAT"]
    assert meta["user"] == "AnPT"


def test_roundtrip_csv_horizontal(tmp_path):
    p = tmp_path / "AnPT_news.csv"
    write_user_csv(p, {"tickers": ["HPG", "FPT"], "industries": ["thep"], "macro": ["my"]})
    doc, meta = read_user_csv(p)
    assert doc["tickers"] == ["HPG", "FPT"]
    assert doc["industries"] == ["THEP"]
    assert doc["macro"] == ["MY"]
    assert meta["user"] == "AnPT"


def test_read_csv_vertical(tmp_path):
    p = tmp_path / "Bob_news.csv"
    content = "category,code,note\ntickers,HPG,Hoa Phat\nindustries,THEP,Nganh Thep\nthemes,LAI_SUAT,Lai suat\n"
    p.write_text(content, encoding="utf-8-sig")
    doc, meta = read_user_csv(p)
    assert doc["tickers"] == ["HPG"]
    assert doc["industries"] == ["THEP"]
    assert doc["themes"] == ["LAI_SUAT"]
    assert meta["user"] == "Bob"


def test_compile_maps_and_reports_unknown(tmp_path):
    reg = k.make_registry()
    inp = tmp_path / "subscriptions"
    inp.mkdir(parents=True)
    # 'hpg' lowercase → chuẩn hoá HPG; ZZZ không có trong danh sách → unknown.
    csv_file = inp / "AnPT_news.csv"
    write_user_csv(csv_file, {"tickers": ["hpg", "FPT", "ZZZ"]}, {"user": "AnPT"})
    cfg = tmp_path / "cfg"
    rec = compile_user("AnPT", csv_file, reg, users_config_dir=cfg, input_dir=inp)

    assert rec["ids"] == {"TICKER:HPG", "TICKER:FPT"}
    assert ("tickers", "ZZZ") in rec["unknown"]
    doc = yaml.safe_load((cfg / "AnPT.yaml").read_text(encoding="utf-8"))
    assert doc["tickers"] == ["HPG", "FPT", "ZZZ"]        # normalized, giữ cả giá trị nhập
    assert (inp / "_unknown" / "AnPT_unknown.txt").exists()


def test_unknown_file_cleared_when_fixed(tmp_path):
    reg = k.make_registry()
    inp = tmp_path / "subscriptions"
    inp.mkdir(parents=True)
    csv_file = inp / "A_news.csv"
    write_user_csv(csv_file, {"tickers": ["ZZZ"]}, {})
    compile_user("A", csv_file, reg, users_config_dir=tmp_path / "cfg", input_dir=inp)
    assert (inp / "_unknown" / "A_unknown.txt").exists()
    # sửa lại đúng → _unknown.txt bị xoá
    write_user_csv(csv_file, {"tickers": ["HPG"]}, {})
    compile_user("A", csv_file, reg, users_config_dir=tmp_path / "cfg", input_dir=inp)
    assert not (inp / "_unknown" / "A_unknown.txt").exists()


def test_compile_all_skips_underscore_and_flat(tmp_path):
    reg = k.make_registry()
    inp = tmp_path / "subscriptions"
    inp.mkdir(parents=True)
    write_user_csv(inp / "AnPT_news.csv", {"tickers": ["HPG"]})
    write_user_csv(inp / "A.csv", {"tickers": ["FPT"]})
    write_user_csv(inp / "_template_news.csv", {"tickers": ["VCB"]})
    cfg = tmp_path / "cfg"

    res = compile_all(inp, reg, users_config_dir=cfg)
    assert {r["name"] for r in res} == {"AnPT", "A"}
    assert (cfg / "AnPT.yaml").exists() and (cfg / "A.yaml").exists()
    assert not (cfg / "_template_news.yaml").exists()


def test_enabled_users_manifest(tmp_path):
    inp = tmp_path / "subscriptions"
    inp.mkdir(parents=True)
    write_user_csv(inp / "AnPT_news.csv", {"tickers": ["HPG"]})
    write_user_csv(inp / "A_news.csv", {"tickers": ["FPT"]})
    write_user_csv(inp / "_template.csv", {"tickers": ["VCB"]})
    (inp / "manifest.yaml").write_text("users:\n  A: false\n", encoding="utf-8")
    assert enabled_users(inp) == {"AnPT"}          # A tắt; _template bỏ; AnPT mặc định bật

