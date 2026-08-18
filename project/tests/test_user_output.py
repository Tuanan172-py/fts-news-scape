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
    # a2: chỉ L1 → loại
    k.seed_article(store, "a2"); k.seed_l1(store, "a2", ["TICKER:HPG"])
    # a3: đủ 2 layer nhưng VNM (không ai đăng ký) → loại
    k.seed_article(store, "a3"); k.seed_l1(store, "a3", ["TICKER:VNM"]); k.seed_agent(store, "a3")

    counts = UserOutputWriter(store, reg, output_root=tmp_path / "out").write(date=DATE)
    assert counts == {"AnPT": 1}

    rows = _read(tmp_path / "out" / "AnPT" / DATE / "final.csv")
    assert len(rows) == 1 and rows[0]["article_id"] == "a1"
    assert rows[0]["matched_entities"] == "HPG"
    assert rows[0]["summary"].startswith("Tóm tắt")
    assert rows[0]["event_type"] == "macro" and rows[0]["impact_area"] == "market"
    # Bob không có bài → không tạo thư mục
    assert not (tmp_path / "out" / "Bob").exists()
    # file per-layer cũng tồn tại
    assert (tmp_path / "out" / "AnPT" / DATE / "L1.csv").exists()
    assert (tmp_path / "out" / "AnPT" / DATE / "agent.csv").exists()


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
    rows = _read(tmp_path / "out" / "AnPT" / DATE / "final.csv")
    assert rows[0]["event_type"] == "" and rows[0]["sentiment"] == ""
    assert rows[0]["summary"].startswith("Tóm tắt")         # field bắt buộc vẫn có


def test_date_filter_excludes_other_day(tmp_path):
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "a1", published="2026-08-17T09:00:00+07:00")
    k.seed_l1(store, "a1", ["TICKER:HPG"]); k.seed_agent(store, "a1")
    counts = UserOutputWriter(store, reg, output_root=tmp_path / "out").write(date=DATE)
    assert counts == {}                                     # bài ngày 17 không vào ngày 18
