"""P1 — compile xlsx → yaml, báo unknown, manifest bật/tắt."""
from __future__ import annotations

import _userkit as k
import yaml

from src.users.compile import (
    compile_all, compile_user, enabled_users, read_user_xlsx, write_user_xlsx,
)


def test_roundtrip_xlsx(tmp_path):
    p = tmp_path / "entities.xlsx"
    write_user_xlsx(p, {"tickers": ["HPG", "FPT"], "industries": ["thep"]}, {"user": "AnPT"})
    doc, meta = read_user_xlsx(p)
    # industries dùng CODE → chuẩn hoá viết hoa như các nhóm mã khác
    assert doc["tickers"] == ["HPG", "FPT"] and doc["industries"] == ["THEP"]
    assert meta["user"] == "AnPT"


def test_compile_maps_and_reports_unknown(tmp_path):
    reg = k.make_registry()
    inp = tmp_path / "input" / "AnPT"
    inp.mkdir(parents=True)
    # 'hpg' lowercase → chuẩn hoá HPG; ZZZ không có trong danh sách → unknown.
    write_user_xlsx(inp / "entities.xlsx", {"tickers": ["hpg", "FPT", "ZZZ"]}, {"user": "AnPT"})
    cfg = tmp_path / "cfg"
    rec = compile_user("AnPT", inp / "entities.xlsx", reg, users_config_dir=cfg, input_dir=inp)

    assert rec["ids"] == {"TICKER:HPG", "TICKER:FPT"}
    assert ("tickers", "ZZZ") in rec["unknown"]
    doc = yaml.safe_load((cfg / "AnPT.yaml").read_text(encoding="utf-8"))
    assert doc["tickers"] == ["HPG", "FPT", "ZZZ"]        # normalized, giữ cả giá trị nhập
    assert (inp / "_unknown.txt").exists()


def test_unknown_file_cleared_when_fixed(tmp_path):
    reg = k.make_registry()
    inp = tmp_path / "input" / "A"
    inp.mkdir(parents=True)
    write_user_xlsx(inp / "entities.xlsx", {"tickers": ["ZZZ"]}, {})
    compile_user("A", inp / "entities.xlsx", reg, users_config_dir=tmp_path / "cfg", input_dir=inp)
    assert (inp / "_unknown.txt").exists()
    # sửa lại đúng → _unknown.txt bị xoá
    write_user_xlsx(inp / "entities.xlsx", {"tickers": ["HPG"]}, {})
    compile_user("A", inp / "entities.xlsx", reg, users_config_dir=tmp_path / "cfg", input_dir=inp)
    assert not (inp / "_unknown.txt").exists()


def test_compile_all_skips_underscore(tmp_path):
    reg = k.make_registry()
    inp = tmp_path / "input"
    for name, tk in [("AnPT", ["HPG"]), ("A", ["FPT"])]:
        d = inp / name
        d.mkdir(parents=True)
        write_user_xlsx(d / "entities.xlsx", {"tickers": tk}, {"user": name})
    (inp / "_draft").mkdir()
    write_user_xlsx(inp / "_draft" / "entities.xlsx", {"tickers": ["VCB"]}, {})
    cfg = tmp_path / "cfg"

    res = compile_all(inp, reg, users_config_dir=cfg)
    assert {r["name"] for r in res} == {"AnPT", "A"}
    assert (cfg / "AnPT.yaml").exists() and (cfg / "A.yaml").exists()
    assert not (cfg / "_draft.yaml").exists()


def test_enabled_users_manifest(tmp_path):
    inp = tmp_path / "input"
    for name in ("AnPT", "A"):
        (inp / name).mkdir(parents=True)
    (inp / "_skip").mkdir()
    (inp / "manifest.yaml").write_text("users:\n  A: false\n", encoding="utf-8")
    assert enabled_users(inp) == {"AnPT"}          # A tắt; _skip bỏ; AnPT mặc định bật
