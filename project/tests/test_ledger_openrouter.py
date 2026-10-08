"""Kiểm định sổ cái đọc usage từ meta cho runner ngoài DSH (E2).

agy và openrouter chạy ngoài DSH nên không có phiên worker để quy kết; sổ cái
phải cộng trực tiếp `usage` trong `*.meta.json` của đợt.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import token_ledger  # noqa: E402

SCHEMA = """CREATE TABLE token_ledger (
    ts TEXT, wave TEXT, batch_id TEXT, agent_id TEXT, n_items INTEGER,
    n_sessions INTEGER, miss_tokens INTEGER, hit_tokens INTEGER,
    out_tokens INTEGER, reasoning_tokens INTEGER, quota_tokens INTEGER,
    turns_max INTEGER, ctx_peak INTEGER, ctx_pct REAL, est_miss INTEGER,
    est_out INTEGER, billed_usd REAL, peak_window INTEGER, note TEXT)"""


class _Glob:
    def __init__(self, files):
        self._files = files

    def glob(self, pattern):
        return self._files


def _run(source, metas, monkeypatch, tmp_path):
    db = str(tmp_path / "ledger.db")
    conn = sqlite3.connect(db)
    conn.execute(SCHEMA)
    conn.commit()
    conn.close()
    monkeypatch.setattr(token_ledger, "glob", _Glob(metas))
    monkeypatch.setattr(token_ledger, "connect", lambda _db: sqlite3.connect(db))
    args = argparse.Namespace(wave="W-E2", batch=None, items=10, est_miss=None,
                              est_out=None, since=0.0, window_min=60,
                              workers_only=False, source=source, db=db,
                              cwd_filter=None, no_reasoning=False, peak=None,
                              note=None, agent="x")
    assert token_ledger.cmd_append(args) == 0
    out = sqlite3.connect(db)
    try:
        return out.execute(
            "SELECT agent_id, miss_tokens, out_tokens, reasoning_tokens,"
            " quota_tokens, billed_usd, note FROM token_ledger").fetchall()
    finally:
        out.close()


def _meta(tmp_path, name, usage):
    p = tmp_path / name
    p.write_text(json.dumps({"usage": usage}), encoding="utf-8")
    return str(p)


def test_ledger_cong_usage_openrouter(tmp_path, monkeypatch):
    """prompt/completion từ meta openrouter vào đúng cột, chi phí theo cost."""
    m1 = _meta(tmp_path, "a.meta.json",
               {"prompt_tokens": 1000, "completion_tokens": 200,
                "total_tokens": 1200, "cost": 0,
                "completion_tokens_details": {"reasoning_tokens": 5}})
    m2 = _meta(tmp_path, "b.meta.json",
               {"prompt_tokens": 500, "completion_tokens": 100,
                "total_tokens": 600, "cost": 0,
                "completion_tokens_details": {"reasoning_tokens": 0}})
    rows = _run("openrouter", [m1, m2], monkeypatch, tmp_path)
    assert rows == [("article-processor-openrouter", 1500, 300, 5, 1800, 0.0,
                     "runner=openrouter")]


def test_ledger_giu_nguyen_nhanh_agy(tmp_path, monkeypatch):
    """Nhánh agy cũ không đổi: input/output tokens và đơn giá cố định."""
    m = _meta(tmp_path, "a.meta.json", {"input_tokens": 1000, "output_tokens": 200})
    rows = _run("agy", [m], monkeypatch, tmp_path)
    assert rows[0][:5] == ("article-processor-agy", 1000, 200, 0, 1200)
    assert rows[0][6] == "runner=agy"


def _pmeta(tmp_path, name, provider, usage, items=0):
    p = tmp_path / name
    p.write_text(json.dumps({"agent_provider": provider, "usage": usage,
                             "items_valid": items}), encoding="utf-8")
    return str(p)


def _rows(db):
    out = sqlite3.connect(db)
    try:
        return out.execute("SELECT agent_id, n_items, miss_tokens, hit_tokens, out_tokens,"
                           " note FROM token_ledger ORDER BY agent_id").fetchall()
    finally:
        out.close()


def test_ledger_tach_dong_theo_provider_cua_tung_meta(tmp_path, monkeypatch):
    """Đợt chạy agy rồi vá bằng openrouter ghi hai dòng, mỗi provider đúng phần của mình."""
    m1 = _pmeta(tmp_path, "a.meta.json", "agy",
                {"input_tokens": 1000, "output_tokens": 200, "cache_read_tokens": 400}, 40)
    m2 = _pmeta(tmp_path, "b.meta.json", "openrouter",
                {"prompt_tokens": 500, "completion_tokens": 100, "cost": 0,
                 "prompt_tokens_details": {"cached_tokens": 300}}, 10)
    _run("auto", [m1, m2], monkeypatch, tmp_path)
    assert _rows(str(tmp_path / "ledger.db")) == [
        ("article-processor-agy", 40, 600, 400, 200, "runner=agy"),
        ("article-processor-openrouter", 10, 200, 300, 100, "runner=openrouter"),
    ]


def test_ledger_opencode_khong_usage_van_ghi_dong(tmp_path, monkeypatch):
    """opencode không ghi số token: vẫn có dòng để thấy số lô, kèm ghi chú thiếu usage."""
    m = _pmeta(tmp_path, "a.meta.json", "opencode-native",
               {"note": "free-tier"}, 50)
    _run("auto", [m], monkeypatch, tmp_path)
    rows = _rows(str(tmp_path / "ledger.db"))
    assert rows == [("article-processor-opencode-native", 10, 0, 0, 0,
                     "runner=opencode-native usage=không ghi")]


def test_ledger_chay_lai_thay_moi_dong_runner_cu(tmp_path, monkeypatch):
    """Chạy lại `--finish` sau khi đổi provider không để lại dòng của provider cũ."""
    m1 = _pmeta(tmp_path, "a.meta.json", "agy", {"input_tokens": 10, "output_tokens": 1})
    _run("auto", [m1], monkeypatch, tmp_path)
    m2 = _pmeta(tmp_path, "b.meta.json", "openrouter",
                {"prompt_tokens": 5, "completion_tokens": 1, "cost": 0})
    monkeypatch.setattr(token_ledger, "glob", _Glob([m2]))
    db = str(tmp_path / "ledger.db")
    monkeypatch.setattr(token_ledger, "connect", lambda _db: sqlite3.connect(db))
    args = argparse.Namespace(wave="W-E2", batch=None, items=10, est_miss=None,
                              est_out=None, since=0.0, window_min=60, workers_only=False,
                              source="auto", db=db, cwd_filter=None, no_reasoning=False,
                              peak=None, note=None, agent="x")
    assert token_ledger.cmd_append(args) == 0
    assert [r[0] for r in _rows(db)] == ["article-processor-openrouter"]
