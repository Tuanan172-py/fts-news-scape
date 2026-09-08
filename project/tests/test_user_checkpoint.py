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

    final = tmp_path / "out" / "AnPT" / f"{DATE}.csv"
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

    rows = _read(tmp_path / "out" / "AnPT" / f"{DATE}.csv")
    ids = sorted(r["article_id"] for r in rows)
    assert ids == ["a1", "a2"]                              # đủ 2, không trùng
    cp = json.loads((tmp_path / "out" / "AnPT" / "_checkpoint.json").read_text(encoding="utf-8"))
    assert set(cp["written"][DATE]) == {"a1", "a2"}


def test_checkpoint_records_gold_status_and_upgrade(tmp_path):
    """Bài giao ở L1_ONLY rồi Gold về sau -> checkpoint đổi trạng thái, filter_upgraded bắt được."""
    from src.export import checkpoint as ckpt

    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "a1"); k.seed_l1(store, "a1", ["TICKER:HPG"])   # chưa có Gold
    w = UserOutputWriter(store, reg, output_root=tmp_path / "out")
    w.write(date=DATE)

    user_dir = tmp_path / "out" / "AnPT"
    cp = json.loads((user_dir / "_checkpoint.json").read_text(encoding="utf-8"))
    assert cp["written"][DATE] == {"a1": "L1_ONLY"}
    assert _read(user_dir / f"{DATE}.csv")[0]["summary"] == ""

    k.seed_agent(store, "a1")                                            # Gold về ở vòng sau
    assert ckpt.filter_upgraded(user_dir, DATE, {"a1": "GOLD"}) == ["a1"]
    w.write(date=DATE)

    cp = json.loads((user_dir / "_checkpoint.json").read_text(encoding="utf-8"))
    assert cp["written"][DATE] == {"a1": "GOLD"}
    rows = _read(user_dir / f"{DATE}.csv")
    assert len(rows) == 1 and rows[0]["summary"].startswith("Tóm tắt")   # ghi đè đầy đủ


def test_checkpoint_reads_legacy_list_format(tmp_path):
    """File checkpoint cũ (list id) vẫn đọc được, không crash, không mất dữ liệu."""
    from src.export import checkpoint as ckpt

    user_dir = tmp_path / "AnPT"
    user_dir.mkdir(parents=True)
    (user_dir / "_checkpoint.json").write_text(
        json.dumps({"written": {DATE: ["old1", "old2"]}}), encoding="utf-8")

    assert ckpt.written_ids(user_dir, DATE) == {"old1", "old2"}
    assert ckpt.filter_new(user_dir, DATE, ["old1", "new1"]) == ["new1"]
    ckpt.mark_written(user_dir, DATE, ["new1"], {"new1": "GOLD"})

    cp = json.loads((user_dir / "_checkpoint.json").read_text(encoding="utf-8"))
    assert cp["written"][DATE] == {"old1": "", "old2": "", "new1": "GOLD"}


def test_locked_output_file_is_not_marked_as_delivered(tmp_path):
    """R3 — file đích bị khoá (Excel): ghi ra snapshot, KHÔNG mark checkpoint, file cũ giữ nguyên."""
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "a1"); k.seed_l1(store, "a1", ["TICKER:HPG"]); k.seed_agent(store, "a1")
    w = UserOutputWriter(store, reg, output_root=tmp_path / "out")
    w.write(date=DATE)

    user_dir = tmp_path / "out" / "AnPT"
    final = user_dir / f"{DATE}.csv"
    k.seed_article(store, "a2"); k.seed_l1(store, "a2", ["TICKER:HPG"]); k.seed_agent(store, "a2")

    with open(final, encoding="utf-8-sig"):                  # giả lập Excel giữ handle
        w.write(date=DATE, write_master=False)

    assert [r["article_id"] for r in _read(final)] == ["a1"]  # file đích VẪN là bản cũ
    snaps = [p for p in user_dir.glob(f"{DATE}_*.csv")]
    assert len(snaps) == 1                                    # dữ liệu mới nằm ở snapshot
    assert {r["article_id"] for r in _read(snaps[0])} == {"a1", "a2"}
    cp = json.loads((user_dir / "_checkpoint.json").read_text(encoding="utf-8"))
    assert "a2" not in cp["written"][DATE]                    # chưa giao → không ghi sổ


def test_mark_written_survives_locked_checkpoint(tmp_path):
    """R2 — checkpoint bị khoá: trả False, không raise (một user hỏng không giết cả vòng lặp)."""
    from src.export import checkpoint as ckpt

    user_dir = tmp_path / "AnPT"
    user_dir.mkdir(parents=True)
    cp_path = user_dir / "_checkpoint.json"
    cp_path.write_text(json.dumps({"written": {DATE: {"a1": "GOLD"}}}), encoding="utf-8")

    with open(cp_path, encoding="utf-8"):
        assert ckpt.mark_written(user_dir, DATE, ["a2"], {"a2": "GOLD"}) is False
    assert ckpt.mark_written(user_dir, DATE, ["a2"], {"a2": "GOLD"}) is True
    assert set(ckpt.written_ids(user_dir, DATE)) == {"a1", "a2"}


def test_no_orphan_tmp_left_in_user_dir(tmp_path):
    """Không để lại file .tmp mồ côi trong thư mục giao hàng của user."""
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "a1"); k.seed_l1(store, "a1", ["TICKER:HPG"]); k.seed_agent(store, "a1")
    UserOutputWriter(store, reg, output_root=tmp_path / "out").write(date=DATE)
    assert list((tmp_path / "out").rglob("*.tmp")) == []
