"""P3 — checkpoint/resume: idempotent, không nhân đôi, thêm bài mới đúng."""
from __future__ import annotations

import csv
import json

import _userkit as k

from src.export.user_output import UserOutputWriter

DATE = "2026-08-18"


def _read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_idempotent_double_write(tmp_path):
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "a1"); k.seed_l1(store, "a1", ["TICKER:HPG"]); k.seed_agent(store, "a1")
    w = UserOutputWriter(store, reg, output_root=tmp_path / "out")
    w.write(date=DATE)
    w.write(date=DATE)                                       # chạy lại

    final = tmp_path / "out" / "AnPT" / DATE / "final.csv"
    assert len(_read(final)) == 1                            # không nhân đôi
    cp = json.loads((tmp_path / "out" / "AnPT" / "_checkpoint.json").read_text(encoding="utf-8"))
    assert "a1" in cp["written"][DATE]


def test_resume_adds_new_article(tmp_path):
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "a1"); k.seed_l1(store, "a1", ["TICKER:HPG"]); k.seed_agent(store, "a1")
    w = UserOutputWriter(store, reg, output_root=tmp_path / "out")
    w.write(date=DATE)

    # bài mới đủ 2 layer xuất hiện sau đó
    k.seed_article(store, "a2"); k.seed_l1(store, "a2", ["TICKER:HPG"]); k.seed_agent(store, "a2")
    w.write(date=DATE)

    rows = _read(tmp_path / "out" / "AnPT" / DATE / "final.csv")
    ids = sorted(r["article_id"] for r in rows)
    assert ids == ["a1", "a2"]                              # đủ 2, không trùng
    cp = json.loads((tmp_path / "out" / "AnPT" / "_checkpoint.json").read_text(encoding="utf-8"))
    assert set(cp["written"][DATE]) == {"a1", "a2"}
