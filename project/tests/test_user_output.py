"""P2 — writer: gate đủ 2 layer, định tuyến subscriber, flatten null-safe."""
from __future__ import annotations

import csv

import _userkit as k

from src.export.user_output import UserOutputWriter

DATE = "2026-08-18"


def _read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_gate_and_routing(tmp_path):
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}, "Bob": {"TICKER:VCB"}})
    # a1: đủ 2 layer, HPG → chỉ AnPT
    k.seed_article(store, "a1"); k.seed_l1(store, "a1", ["TICKER:HPG"]); k.seed_agent(store, "a1")
    # a2: chỉ L1, HPG → gate nới lỏng: AnPT vẫn nhận, các trường gold để trống ""
    k.seed_article(store, "a2"); k.seed_l1(store, "a2", ["TICKER:HPG"])
    # a3: đủ 2 layer nhưng VNM (không ai đăng ký) → loại
    k.seed_article(store, "a3"); k.seed_l1(store, "a3", ["TICKER:VNM"]); k.seed_agent(store, "a3")

    counts = UserOutputWriter(store, reg, output_root=tmp_path / "out").write(date=DATE)
    assert counts == {"AnPT": 2}

    # Đọc trực tiếp kiểm tra header column order trên file phẳng 2026-08-18.csv
    out_file = tmp_path / "out" / "AnPT" / f"{DATE}.csv"
    with open(out_file, encoding="utf-8-sig", newline="") as f:
        header = next(csv.reader(f))
    assert header[0] == "date"
    assert header[1] == "matched_entities"
    assert header[2] == "title"
    assert "materiality_score" not in header
    assert header[-3:] == ["article_id", "agent_provider", "model_used"]

    rows = _read(out_file)
    assert len(rows) == 2
    row_map = {r["article_id"]: r for r in rows}

    # a1: đủ gold
    assert row_map["a1"]["date"] == DATE
    assert row_map["a1"]["matched_entities"] == "HPG"
    assert row_map["a1"]["summary"].startswith("Tóm tắt")
    assert row_map["a1"]["key_points"].startswith("- ")
    assert row_map["a1"]["event_type"] == "macro" and row_map["a1"]["impact_area"] == "market"
    assert "materiality_score" not in row_map["a1"]
    assert row_map["a1"]["agent_provider"] == "p"
    assert row_map["a1"]["model_used"] == "m"

    # a2: chỉ L1, thiếu gold -> các trường gold để ""
    assert row_map["a2"]["date"] == DATE
    assert row_map["a2"]["matched_entities"] == "HPG"
    assert row_map["a2"]["summary"] == ""
    assert row_map["a2"]["key_points"] == ""
    assert row_map["a2"]["implication"] == ""
    assert row_map["a2"]["impact_area"] == ""
    assert "materiality_score" not in row_map["a2"]
    assert row_map["a2"]["time_sensitivity"] == ""
    assert row_map["a2"]["sentiment"] == ""
    assert row_map["a2"]["event_type"] == ""
    assert row_map["a2"]["agent_provider"] == ""
    assert row_map["a2"]["model_used"] == ""

    # Bob không có bài → không tạo thư mục
    assert not (tmp_path / "out" / "Bob").exists()
    # Thư mục user chỉ có duy nhất {DATE}.csv phẳng (không lồng subfolder ngày)
    assert out_file.exists()
    assert not (tmp_path / "out" / "AnPT" / DATE).exists()
    # Thư mục _master có các file audit phẳng
    assert (tmp_path / "out" / "_master" / f"{DATE}.csv").exists()
    assert (tmp_path / "out" / "_master" / f"{DATE}_L1.csv").exists()
    assert (tmp_path / "out" / "_master" / f"{DATE}_agent.csv").exists()
    # _master/_agent.csv chỉ ghi nhận các bài thực sự có output gold (a1 và a3)
    master_agents = _read(tmp_path / "out" / "_master" / f"{DATE}_agent.csv")
    assert {r["article_id"] for r in master_agents} == {"a1", "a3"}


def test_enabled_filter(tmp_path):
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}, "Bob": {"TICKER:HPG"}})
    k.seed_article(store, "a1"); k.seed_l1(store, "a1", ["TICKER:HPG"]); k.seed_agent(store, "a1")
    # chỉ bật AnPT → Bob bị loại dù cùng đăng ký HPG
    counts = UserOutputWriter(store, reg, output_root=tmp_path / "out",
                              enabled={"AnPT"}).write(date=DATE)
    assert counts == {"AnPT": 1}
    assert not (tmp_path / "out" / "Bob").exists()


def test_flatten_null_safe(tmp_path):
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "a1"); k.seed_l1(store, "a1", ["TICKER:HPG"])
    k.seed_agent(store, "a1", with_optional=False)          # thiếu sentiment/event_type
    UserOutputWriter(store, reg, output_root=tmp_path / "out").write(date=DATE)
    rows = _read(tmp_path / "out" / "AnPT" / f"{DATE}.csv")
    assert rows[0]["event_type"] == "" and rows[0]["sentiment"] == ""
    assert rows[0]["summary"].startswith("Tóm tắt")         # field bắt buộc vẫn có


def test_date_filter_excludes_other_day(tmp_path):
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "a1", published="2026-08-17T09:00:00+07:00")
    k.seed_l1(store, "a1", ["TICKER:HPG"]); k.seed_agent(store, "a1")
    counts = UserOutputWriter(store, reg, output_root=tmp_path / "out").write(date=DATE)
    assert counts == {}                                     # bài ngày 17 không vào ngày 18


def test_l1_only_export_fallback_empty_gold(tmp_path):
    """Bài chỉ có L1 (chưa có Gold) vẫn đạt gate export, mọi trường Gold đều là chuỗi rỗng."""
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "art_l1_only", title="Bài viết thử nghiệm")
    k.seed_l1(store, "art_l1_only", ["TICKER:HPG"])
    # Không seed agent_output

    writer = UserOutputWriter(store, reg, output_root=tmp_path / "out")
    counts = writer.write(date=DATE)
    assert counts == {"AnPT": 1}

    rows = _read(tmp_path / "out" / "AnPT" / f"{DATE}.csv")
    assert len(rows) == 1
    r = rows[0]
    assert r["article_id"] == "art_l1_only"
    assert r["title"] == "Bài viết thử nghiệm"
    assert r["matched_entities"] == "HPG"
    # Mọi trường Gold đều là ""
    assert r["summary"] == ""
    assert r["key_points"] == ""
    assert r["implication"] == ""
    assert r["impact_area"] == ""
    assert "materiality_score" not in r
    assert r["time_sensitivity"] == ""
    assert r["sentiment"] == ""
    assert r["event_type"] == ""
    assert r["agent_provider"] == ""
    assert r["model_used"] == ""


