"""Ghi KPI từng tác nhân của một đợt vào `agent_metrics` của harness, tính từ vết."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from src.ops.config import OpsPaths
from src.ops.store import OpsStore

VN_TZ = timezone(timedelta(hours=7))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_id TEXT NOT NULL, run_ts TEXT NOT NULL,
  items INTEGER NOT NULL DEFAULT 0, dod_pass INTEGER NOT NULL DEFAULT 0,
  dod_total INTEGER NOT NULL DEFAULT 0, tokens INTEGER,
  fp_flags INTEGER NOT NULL DEFAULT 0, wave TEXT, note TEXT, created_at TEXT NOT NULL
);
"""


def wave_numbers(store: OpsStore, wave_id: str) -> dict:
    """Tính các số đo của một đợt từ ops_spans.

    Args:
        store: Store vận hành.
        wave_id: Mã đợt.

    Returns:
        Từ điển: tổng bài, bài nhận được sau lượt đầu và cuối cùng, token từng pha.
    """
    with store.conn() as c:
        steps = c.execute("SELECT name, attrs_json FROM ops_spans WHERE trace_id = ? AND kind = 'step' "
                          "ORDER BY started_at", (wave_id,)).fetchall()
        agents = c.execute("SELECT s.attrs_json, p.name AS step FROM ops_spans s "
                           "LEFT JOIN ops_spans p ON p.span_id = s.parent_id "
                           "WHERE s.trace_id = ? AND s.kind = 'agent'", (wave_id,)).fetchall()
    total = first = last = 0
    for st in steps:
        a = json.loads(st["attrs_json"] or "{}")
        if st["name"] == "analyze" and a.get("total"):
            total, first = int(a["total"]), int(a.get("received") or 0)
        if st["name"].startswith(("analyze", "repair")) and a.get("total"):
            total, last = int(a["total"]), int(a.get("received") or 0)
    tokens = repair_tokens = tool_calls = denied = 0
    for ag in agents:
        a = json.loads(ag["attrs_json"] or "{}")
        t = int((a.get("usage") or {}).get("total_tokens") or 0)
        tokens += t
        if str(ag["step"] or "").startswith("repair"):
            repair_tokens += t
        tool_calls += int(bool(a.get("tool_invoked")))
        denied += int(bool(a.get("denied_actions")))
    return {"total": total, "first_pass": first, "final": last, "tokens": tokens,
            "repair_tokens": repair_tokens, "tool_calls": tool_calls, "denied": denied}


def record_wave(paths: OpsPaths, store: OpsStore, wave_id: str, status: str) -> int:
    """Ghi một dòng `agent_metrics` cho mỗi tác nhân tham gia đợt.

    Args:
        paths: Đường dẫn vận hành (chứa `harness_db`).
        store: Store vận hành.
        wave_id: Mã đợt.
        status: Trạng thái cuối của đợt.

    Returns:
        Số dòng đã ghi.
    """
    n = wave_numbers(store, wave_id)
    total = n["total"]
    if not total:
        return 0
    ts = datetime.now(VN_TZ).isoformat(timespec="seconds")
    note = (f"status={status} first_pass={n['first_pass']}/{total} "
            f"repair_tokens={n['repair_tokens']} tool_calls={n['tool_calls']} denied={n['denied']}")
    final = n["final"] or n["first_pass"]
    rows = [
        ("article-packer", total, total, total, None),
        ("article-processor", total, final, total, n["tokens"]),
        ("article-expander", total, final if status == "DONE" else 0, total, None),
    ]
    paths.harness_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(paths.harness_db), timeout=10)
    try:
        conn.executescript(_SCHEMA)
        conn.execute("DELETE FROM agent_metrics WHERE wave = ?", (wave_id,))
        conn.executemany(
            "INSERT INTO agent_metrics(agent_id, run_ts, items, dod_pass, dod_total, tokens, "
            "fp_flags, wave, note, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(a, ts, items, ok, tot, tok, 0, wave_id, note, ts) for a, items, ok, tot, tok in rows])
        conn.commit()
    finally:
        conn.close()
    return len(rows)
