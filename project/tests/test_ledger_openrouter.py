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
