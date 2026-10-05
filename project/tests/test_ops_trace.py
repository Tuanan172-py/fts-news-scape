"""Kiểm thử P0 của US-031: vết span, KPI từng tác nhân và điều kiện không ghi khi chạy tay."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.ops import trace as tracing
from src.ops.config import load_config, resolve_paths
from src.ops.procrun import StepResult
from src.ops.store import OpsStore
from src.ops.trace import Tracer
from src.ops.wave_flow import DirectOps, WaveSpec, WaveSteps, drive_wave


@pytest.fixture
def env(tmp_path):
    cfg = load_config()
    paths = resolve_paths(tmp_path / "data")
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    return cfg, paths, OpsStore(paths.ops_db, log_dir=paths.log_dir)


def _spans(path, where="1=1"):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(f"SELECT * FROM ops_spans WHERE {where} ORDER BY started_at")]
    finally:
        conn.close()


# ── Tracer ───────────────────────────────────────────────────────────────────
def test_tracer_merges_attrs_and_replays_idempotently(env):
    _, paths, _ = env
    tr = Tracer(paths.ops_db, "W1")
    sid = tr.begin("analyze", "step", "article-processor", span_id="W1.a0.analyze", mode="analyze")
    assert sid == "W1.a0.analyze"
    tr.finish(sid, "ok", received=56, total=100, output_ref="x.json")
    tr.begin("analyze", "step", "article-processor", span_id="W1.a0.analyze", mode="analyze")
    rows = _spans(paths.ops_db)
    assert len(rows) == 1 and rows[0]["status"] == "running"
    tr.finish(sid, "ok", received=56, total=100)
    row = _spans(paths.ops_db)[0]
    attrs = json.loads(row["attrs_json"])
    assert attrs == {"mode": "analyze", "received": 56, "total": 100}
    assert row["skill"] == "l1-entity-matcher" and row["actor_id"] == "article-processor"


def test_close_running_marks_orphans_but_not_workflow_root(env):
    _, paths, _ = env
    tr = Tracer(paths.ops_db, "W1")
    tr.begin("wave-W1", "workflow", span_id="W1.a0", parent_id=None)
    tr.begin("analyze", "step", span_id="W1.a0.analyze")
    assert tr.close_running() == 1
    by = {r["span_id"]: r["status"] for r in _spans(paths.ops_db)}
    assert by == {"W1.a0": "running", "W1.a0.analyze": "interrupted"}


def test_span_is_noop_without_env(tmp_path, monkeypatch):
    for k in (tracing.ENV_DB, tracing.ENV_WAVE, tracing.ENV_PARENT):
        monkeypatch.delenv(k, raising=False)
    with tracing.span("x", "script") as sp:
        sp.set(a=1)
        assert sp.id is None and sp.env() == {}
    assert tracing.from_env() is None


def test_span_with_env_records_failure_and_reraises(env, monkeypatch):
    _, paths, _ = env
    monkeypatch.setenv(tracing.ENV_DB, str(paths.ops_db))
    monkeypatch.setenv(tracing.ENV_WAVE, "W9")
    monkeypatch.setenv(tracing.ENV_PARENT, "W9.a0.finish")
    with pytest.raises(RuntimeError):
        with tracing.span("boom.py", "script", span_id="W9.a0.finish/boom.py"):
            raise RuntimeError("x")
    row = _spans(paths.ops_db)[0]
    assert row["status"] == "fail" and row["parent_id"] == "W9.a0.finish"


def test_tracing_failure_never_breaks_caller(tmp_path):
    bad = Tracer(tmp_path / "no" / "such" / "dir" / "ops.db", "W1")
    assert bad.begin("x", "step") is None
    bad.finish(None)
    with tracing.span("x", "step", tracer=bad) as sp:
        assert sp.id is None


# ── Chạy tay không ghi gì (điều kiện nghiệm thu P0) ──────────────────────────
def test_manual_article_run_helper_writes_nothing(tmp_path, monkeypatch):
    from scripts import article_run as ar

    for k in (tracing.ENV_DB, tracing.ENV_WAVE, tracing.ENV_PARENT):
        monkeypatch.delenv(k, raising=False)
    script = tmp_path / "noop.py"
    script.write_text("print('ok')", encoding="utf-8")
    assert ar.run([sys.executable, str(script)], cwd=tmp_path) == 0
    assert list(tmp_path.glob("*.db")) == []


def test_article_run_helper_records_script_span_under_daemon_parent(env, monkeypatch, tmp_path):
    from scripts import article_run as ar

    _, paths, _ = env
    monkeypatch.setenv(tracing.ENV_DB, str(paths.ops_db))
    monkeypatch.setenv(tracing.ENV_WAVE, "W5")
    monkeypatch.setenv(tracing.ENV_PARENT, "W5.a0.finish")
    script = tmp_path / "article_expand.py"
    script.write_text("import sys; sys.exit(0)", encoding="utf-8")
    ar.run([sys.executable, str(script)], cwd=tmp_path)
    row = _spans(paths.ops_db)[0]
    assert row["name"] == "article_expand.py" and row["kind"] == "script"
    assert row["actor_id"] == "article-expander" and row["parent_id"] == "W5.a0.finish"
    assert row["status"] == "ok" and json.loads(row["attrs_json"])["rc"] == 0


# ── AgyRunner: span cho từng lô ──────────────────────────────────────────────
def _agy_stdout(records, usage):
    events = [{"type": "result", "result": {"response": json.dumps(records, ensure_ascii=False),
                                              "usage": usage}}]
    return "\n".join(json.dumps(e, ensure_ascii=False) for e in events)


def test_agy_batch_records_agent_span_with_tool_flags(env, monkeypatch, tmp_path):
    from src.agent.agy_runner import AgyRunner

    _, paths, _ = env
    monkeypatch.setenv(tracing.ENV_DB, str(paths.ops_db))
    monkeypatch.setenv(tracing.ENV_WAVE, "W7")
    monkeypatch.setenv(tracing.ENV_PARENT, "W7.a0.analyze")
    packet = {"d": "2026-10-01", "n": 2, "a": [
        {"i": 0, "t": "Tiêu đề một", "p": ["Đoạn văn thứ nhất đủ dài để làm trích dẫn."]},
        {"i": 1, "t": "Tiêu đề hai", "p": ["Đoạn văn thứ hai cũng đủ dài để làm trích dẫn."]}]}
    task = tmp_path / "article_W7_01.task.json"
    task.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    rec = {"i": 0, "e": [], "s": "Tóm tắt có dấu", "k": ["luận điểm một", "luận điểm hai"],
           "im": "Hàm ý thị trường đủ dài để vượt ngưỡng bốn mươi ký tự.",
           "sn": "neu", "ts": "week", "c": [0]}
    usage = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}

    def fake(cmd, stdin, env_, work_dir):
        return SimpleNamespace(stdout=_agy_stdout([rec], usage), stderr="", returncode=0)

    runner = AgyRunner(profile_root=tmp_path / "pr", work_root=tmp_path / "wr")
    res = runner.run_batch("article_W7_01", task, tmp_path / "out", core_text="CORE",
                           mock_subprocess=fake)
    assert res.status == "PARTIAL"
    row = _spans(paths.ops_db)[0]
    a = json.loads(row["attrs_json"])
    assert row["kind"] == "agent" and row["span_id"] == "W7.a0.analyze/article_W7_01"
    assert row["status"] == "partial" and row["actor_id"] == "article-processor"
    assert a["usage"]["total_tokens"] == 120 and a["items"] == 1 and a["items_total"] == 2
    assert a["tool_invoked"] is False and a["denied_actions"] is False and a["attempts"] == 1


# ── Một đợt qua WaveSteps: cây vết và KPI ────────────────────────────────────
def test_full_wave_builds_trace_tree_and_writes_metrics(env, tmp_path, monkeypatch):
    cfg, paths, store = env
    task_dir = tmp_path / "t"
    task_dir.mkdir()
    seen_env = []

    def fake_exec(cmd, **kw):
        seen_env.append(kw.get("extra_env"))
        if "--check-prefix" in cmd:
            return StepResult(0, "ok", 0.1, "", kw["log_path"])
        if "--limit" in cmd:
            (task_dir / "wave_W1.json").write_text('{"articles": 4, "batches": []}', encoding="utf-8")
            (task_dir / "article_W1_01.map.json").write_text(
                json.dumps({"index": {"0": "a", "1": "b", "2": "c", "3": "d"}}), encoding="utf-8")
            return StepResult(0, "ok", 0.1, "", kw["log_path"])
        if "--analyze" in cmd:
            return StepResult(1, "failed", 0.1, "  ⚠️ article_W1_01: PARTIAL (2 bài)", kw["log_path"])
        if "--repair" in cmd:
            return StepResult(0, "ok", 0.1, "  ✅ article_W1_01_r01: OK (2 bài)", kw["log_path"])
        return StepResult(0, "ok", 0.1, "", kw["log_path"])

    steps = WaveSteps(store, cfg, paths, executor=fake_exec, task_dir=task_dir,
                      out_dir=tmp_path / "o", db_probe=lambda: (True, ""))
    cov = iter([(0, 4), (2, 4), (2, 4), (4, 4)])
    monkeypatch.setattr(steps, "_coverage", lambda w: next(cov))
    spec = WaveSpec("W1", "2026-10-01", "T1", "L1")
    store.upsert_wave("W1", status="SENSED", level="L1", provider="agy")

    # Lượt hai của analyze phải thành repair vì đã có đầu ra.
    calls = {"n": 0}

    def has_outputs(w):
        calls["n"] += 1
        return calls["n"] > 1

    monkeypatch.setattr(steps, "_has_outputs", has_outputs)
    assert drive_wave(spec.__dict__, DirectOps(steps), cfg) == "DONE"

    spans = {s["span_id"]: s for s in _spans(paths.ops_db, "trace_id = 'W1'")}
    root = spans["W1.a0"]
    assert root["kind"] == "workflow" and root["parent_id"] is None and root["status"] == "ok"
    for step in ("preflight", "prepare", "analyze", "repair1", "finish"):
        s = spans[f"W1.a0.{step}"]
        assert s["kind"] == "step" and s["parent_id"] == "W1.a0"
        # Lượt analyze đầu thoát mã 1 vì lô mới nhận một phần; các bước còn lại thành công.
        assert s["status"] == ("fail" if step == "analyze" else "ok"), step
    assert spans["W1.a0.prepare"]["actor_id"] == "article-packer"
    assert spans["W1.a0.finish"]["actor_id"] == "article-expander"
    first = json.loads(spans["W1.a0.analyze"]["attrs_json"])
    assert first["received"] == 2 and first["total"] == 4
    # Mọi tiến trình con nhận ngữ cảnh ghi vết trỏ về span bước của nó.
    env_parents = [e[tracing.ENV_PARENT] for e in seen_env if e]
    assert "W1.a0.analyze" in env_parents and "W1.a0.finish" in env_parents
    assert all(e[tracing.ENV_WAVE] == "W1" for e in seen_env if e)

    conn = sqlite3.connect(paths.harness_db)
    rows = conn.execute("SELECT agent_id, items, dod_pass, dod_total, wave FROM agent_metrics "
                        "ORDER BY agent_id").fetchall()
    conn.close()
    assert [r[0] for r in rows] == ["article-expander", "article-packer", "article-processor"]
    assert all(r[4] == "W1" and r[1] == 4 for r in rows)


def test_metrics_numbers_from_spans(env):
    from src.ops.metrics import wave_numbers

    _, paths, store = env
    tr = Tracer(paths.ops_db, "W2")
    tr.begin("analyze", "step", span_id="W2.a0.analyze")
    tr.finish("W2.a0.analyze", "ok", received=56, total=100)
    tr.begin("repair1", "step", span_id="W2.a0.repair1")
    tr.finish("W2.a0.repair1", "ok", received=100, total=100)
    for sid, parent, tok in (("W2.a0.analyze/b1", "W2.a0.analyze", 60235),
                             ("W2.a0.repair1/b1_r01", "W2.a0.repair1", 49599)):
        tr.begin("lô", "agent", "article-processor", span_id=sid, parent_id=parent)
        tr.finish(sid, "ok", usage={"total_tokens": tok}, tool_invoked=False, denied_actions=False)
    n = wave_numbers(store, "W2")
    assert n == {"total": 100, "first_pass": 56, "final": 100, "tokens": 109834,
                 "repair_tokens": 49599, "tool_calls": 0, "denied": 0}
