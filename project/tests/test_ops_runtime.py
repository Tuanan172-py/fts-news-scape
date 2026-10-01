"""Kiểm thử vòng đời đợt, chạy bước có deadline, supervisor và sentinel của tầng vận hành."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from src.ops import breakers as br
from src.ops.config import load_config, resolve_paths
from src.ops.order import StandingOrder, extend, load_order, save_order
from src.ops.procrun import StepResult, run_step
from src.ops.sentinel import diagnose, parse_diagnosis
from src.ops.store import OpsStore
from src.ops.supervisor import CaptureSupervisor
from src.ops.wave_flow import (DirectOps, WaveSpec, WaveSteps, drive_wave,
                               parse_batch_lines)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def env(tmp_path):
    cfg = load_config()
    paths = resolve_paths(tmp_path / "data")
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    store = OpsStore(paths.ops_db, log_dir=paths.log_dir)
    return cfg, paths, store


# ── drive_wave: logic tất định của máy trạng thái ────────────────────────────
class FakeOps:
    def __init__(self, *, preflight=(True, "", False), n=100, analyses=None,
                 finish_ok=True, stop=False):
        self._pre, self._n = preflight, n
        self._analyses = list(analyses or [dict(received=100, total=100, worst="OK",
                                                step_outcome="ok")])
        self._finish_ok, self._stop = finish_ok, stop
        self.calls: list[str] = []
        self.final: tuple | None = None

    def preflight(self, spec):
        self.calls.append("preflight")
        return list(self._pre)

    def prepare(self, spec):
        self.calls.append("prepare")
        return self._n

    def analyze(self, spec, round_no):
        self.calls.append(f"analyze{round_no}")
        return self._analyses.pop(0) if len(self._analyses) > 1 else self._analyses[0]

    def stop_requested(self, spec):
        self.calls.append("stop_requested")
        return self._stop

    def finish(self, spec):
        self.calls.append("finish")
        return [self._finish_ok, "ok" if self._finish_ok else "failed", "tail"]

    def finalize(self, spec, status, reason, flags):
        self.final = (status, reason, flags)
        return status


def _spec(level="L1"):
    return {"wave_id": "W1", "target_date": "2026-10-01", "trigger": "T1", "level": level,
            "provider": "agy", "attempt": 0, "order_hash": ""}


def test_d10_l1_runs_to_done_without_approval_or_delivery():
    """D10 + D11: đợt chạy trọn tới nạp DB, không hỏi người, không giao xlsx."""
    ops = FakeOps()
    assert drive_wave(_spec("L1"), ops, load_config()) == "DONE"
    assert ops.calls == ["preflight", "prepare", "analyze0", "stop_requested", "finish"]


def test_b6_stop_is_honored_only_at_boundary_before_finish():
    ops = FakeOps(stop=True)
    assert drive_wave(_spec(), ops, load_config()) == "CANCELLED"
    assert "finish" not in ops.calls and ops.final[2]["failure"] is False


def test_repairs_until_complete():
    ops = FakeOps(analyses=[dict(received=80, total=100, worst="EMPTY", step_outcome="failed"),
                            dict(received=100, total=100, worst="OK", step_outcome="ok")])
    assert drive_wave(_spec(), ops, load_config()) == "DONE"
    assert ops.calls.count("analyze0") == 1 and "analyze1" in ops.calls


def test_quota_parks_for_breaker_without_repair_loop():
    ops = FakeOps(analyses=[dict(received=50, total=100, worst="QUOTA", step_outcome="failed")])
    assert drive_wave(_spec(), ops, load_config()) == "PARKED"
    assert ops.final[2]["resume_on_breaker"] is True and ops.final[2]["failure"] is False
    assert "analyze1" not in ops.calls


def test_low_coverage_fatal_counts_as_failure():
    ops = FakeOps(analyses=[dict(received=10, total=100, worst="FATAL", step_outcome="failed")])
    assert drive_wave(_spec(), ops, load_config()) == "PARKED"
    assert ops.final[2]["failure"] is True


def test_preflight_breaker_parks_and_finish_failure_fails():
    ops = FakeOps(preflight=(False, "Breaker OPEN", True))
    assert drive_wave(_spec(), ops, load_config()) == "PARKED"
    assert ops.final[2]["resume_on_breaker"] is True and ops.calls == ["preflight"]
    ops = FakeOps(finish_ok=False)
    assert drive_wave(_spec(), ops, load_config()) == "FAILED"
    assert ops.final[2]["failure"] is True


def test_empty_wave_is_done_and_prepare_error_fails():
    ops = FakeOps(n=0)
    assert drive_wave(_spec(), ops, load_config()) == "DONE"
    assert ops.final[2]["clean"] is False
    assert drive_wave(_spec(), FakeOps(n=-1), load_config()) == "FAILED"


# ── WaveSteps với tiến trình giả ─────────────────────────────────────────────
ANALYZE_LOG = """
 🤖  BẮT ĐẦU PHÂN TÍCH AGY RUNNER
Hoàn tất: 1/2 lô đạt OK, trích xuất 50 bài, 1,000 tokens.
  ✅ article_W1_01: OK (50 bài)
  ⚠️ article_W1_02: QUOTA (0 bài) Hạn mức phiên chạm ngưỡng 429 Resource Exhausted.
"""


def test_parse_batch_lines():
    rows = parse_batch_lines(ANALYZE_LOG)
    assert rows == [("article_W1_01", "OK", 50, ""),
                    ("article_W1_02", "QUOTA", 0,
                     "Hạn mức phiên chạm ngưỡng 429 Resource Exhausted.")]


def test_analyze_records_breaker_and_alerts(env, tmp_path, monkeypatch):
    cfg, paths, store = env

    def fake_exec(cmd, **kw):
        return StepResult(1, "failed", 3.0, ANALYZE_LOG, kw["log_path"])

    steps = WaveSteps(store, cfg, paths, executor=fake_exec, task_dir=tmp_path / "t",
                      out_dir=tmp_path / "o", db_probe=lambda: (True, ""))
    monkeypatch.setattr(steps, "_coverage", lambda w: (50, 100))
    out = steps.analyze(WaveSpec("W1", "2026-10-01", "T1", "L1"), 0)
    assert out.worst == br.QUOTA and out.received == 50 and out.mode == "analyze"
    assert steps.breakers.get("agy").state == "OPEN"
    texts = [a["text"] for a in store.unsent_alerts()]
    assert any("hết hạn mức" in t for t in texts)


def test_analyze_switches_to_repair_when_outputs_exist(env, tmp_path, monkeypatch):
    cfg, paths, store = env
    seen = {}

    def fake_exec(cmd, **kw):
        seen["cmd"] = cmd
        return StepResult(0, "ok", 1.0, "  ✅ article_W1_01_r01: OK (3 bài)", kw["log_path"])

    out_dir = tmp_path / "o"
    out_dir.mkdir()
    (out_dir / "article_W1_01.output.json").write_text("[]", encoding="utf-8")
    steps = WaveSteps(store, cfg, paths, executor=fake_exec, task_dir=tmp_path / "t",
                      out_dir=out_dir, db_probe=lambda: (True, ""))
    monkeypatch.setattr(steps, "_coverage", lambda w: (97, 100))
    out = steps.analyze(WaveSpec("W1", "2026-10-01", "T1", "L1"), 1)
    assert "--repair" in seen["cmd"] and out.mode == "repair"


def test_finalize_demotes_after_consecutive_failures(env):
    cfg, paths, store = env
    save_order(paths.standing_order, extend(StandingOrder(level="L1"), 7, 7))
    steps = WaveSteps(store, cfg, paths, db_probe=lambda: (True, ""))
    spec = WaveSpec("W1", "2026-10-01", "T1", "L1")
    steps.finalize(spec, "FAILED", "cổng đỏ", counts_as_failure=True)
    assert load_order(paths.standing_order).level == "L1"
    steps.finalize(WaveSpec("W2", "2026-10-01", "T1", "L1"), "FAILED", "cổng đỏ",
                   counts_as_failure=True)
    assert load_order(paths.standing_order).level == "L0"
    assert any(a["severity"] == "critical" for a in store.unsent_alerts())


def test_preflight_blocks_on_kill_switch_and_breaker(env):
    cfg, paths, store = env
    steps = WaveSteps(store, cfg, paths, db_probe=lambda: (True, ""))
    spec = WaveSpec("W1", "2026-10-01", "T1", "L1")
    paths.kill_switch.write_text("x", encoding="utf-8")
    ok, reason, wait = steps.preflight(spec)
    assert not ok and "AGY_STOP" in reason and not wait
    paths.kill_switch.unlink()
    steps.breakers.record("agy", br.AUTH)
    ok, reason, wait = steps.preflight(spec)
    assert not ok and wait


def test_direct_ops_full_wave_with_fake_executor(env, tmp_path, monkeypatch):
    """Một đợt L1 trọn vòng với tiến trình giả: prepare ghi manifest, analyze đủ bài."""
    cfg, paths, store = env
    task_dir = tmp_path / "t"
    task_dir.mkdir()

    def fake_exec(cmd, **kw):
        if "--check-prefix" in cmd:
            return StepResult(0, "ok", 0.1, "", kw["log_path"])
        if "--limit" in cmd:
            (task_dir / "wave_W1.json").write_text('{"articles": 2, "batches": []}',
                                                   encoding="utf-8")
            return StepResult(0, "ok", 0.1, "", kw["log_path"])
        if "--analyze" in cmd:
            return StepResult(0, "ok", 0.1, "  ✅ article_W1_01: OK (2 bài)", kw["log_path"])
        return StepResult(0, "ok", 0.1, "✅ ĐỢT W1 HOÀN TẤT", kw["log_path"])

    steps = WaveSteps(store, cfg, paths, executor=fake_exec, task_dir=task_dir,
                      out_dir=tmp_path / "o", db_probe=lambda: (True, ""))
    cov = iter([(0, 2), (2, 2)])
    monkeypatch.setattr(steps, "_coverage", lambda w: next(cov))
    spec = WaveSpec("W1", "2026-10-01", "T1", "L1")
    store.upsert_wave("W1", status="SENSED", level="L1", provider="agy")
    assert drive_wave(spec.__dict__, DirectOps(steps), cfg) == "DONE"
    w = store.wave("W1")
    assert w["status"] == "DONE" and w["n_articles"] == 2
    assert store.get_state("clean_streak") == "1"


# ── run_step: deadline, treo, huỷ ────────────────────────────────────────────
def _py(code: str) -> list[str]:
    return [sys.executable, "-c", textwrap.dedent(code)]


def test_run_step_ok_and_failed(tmp_path):
    r = run_step(_py("print('xin chào')"), cwd=tmp_path, log_path=tmp_path / "a.log",
                 deadline_s=30, poll_s=0.1)
    assert r.ok and "xin chào" in r.tail
    r = run_step(_py("import sys; sys.exit(3)"), cwd=tmp_path, log_path=tmp_path / "b.log",
                 deadline_s=30, poll_s=0.1)
    assert r.outcome == "failed" and r.returncode == 3


def test_run_step_tail_only_covers_current_run(tmp_path):
    log = tmp_path / "a.log"
    run_step(_py("print('LẦN TRƯỚC FATAL')"), cwd=tmp_path, log_path=log, deadline_s=30,
             poll_s=0.1)
    r = run_step(_py("print('LẦN NÀY OK')"), cwd=tmp_path, log_path=log, deadline_s=30,
                 poll_s=0.1)
    assert "LẦN NÀY OK" in r.tail and "LẦN TRƯỚC" not in r.tail


def test_run_step_timeout_kills_child_tree(tmp_path):
    code = """
    import subprocess, sys, time
    subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    time.sleep(60)
    """
    r = run_step(_py(code), cwd=tmp_path, log_path=tmp_path / "c.log", deadline_s=2,
                 poll_s=0.2)
    assert r.outcome == "timeout" and r.duration_s < 30


def test_run_step_stalled_and_cancelled(tmp_path):
    r = run_step(_py("import time; time.sleep(60)"), cwd=tmp_path,
                 log_path=tmp_path / "d.log", deadline_s=60, progress_fn=lambda: 0,
                 silence_s=1.5, poll_s=0.2)
    assert r.outcome == "stalled"
    flag = tmp_path / "stop"
    flag.write_text("1")
    r = run_step(_py("import time; time.sleep(60)"), cwd=tmp_path,
                 log_path=tmp_path / "e.log", deadline_s=60, stop_fn=flag.exists, poll_s=0.2)
    assert r.outcome == "cancelled"


# ── supervisor ───────────────────────────────────────────────────────────────
class FakeProc:
    _pid = 100

    def __init__(self):
        FakeProc._pid += 1
        self.pid = FakeProc._pid
        self.rc = None

    def poll(self):
        return self.rc


def test_supervisor_restarts_with_backoff_then_gives_up(env):
    cfg, paths, store = env
    clock = [0.0]
    procs: list[FakeProc] = []

    def spawn():
        p = FakeProc()
        procs.append(p)
        return p

    sup = CaptureSupervisor(store, {**cfg["supervisor"], "max_restarts": 3,
                                    "restart_backoff_seconds": [10]},
                            paths.data_dir / "capture.lock", paths.log_dir / "c.log",
                            spawn=spawn, lock_held=lambda _p: False, clock=lambda: clock[0])
    assert sup.tick() == "child" and len(procs) == 1
    for _ in range(2):
        procs[-1].rc = 1
        assert sup.tick() == "backoff"
        clock[0] += 11
        assert sup.tick() == "child"
    procs[-1].rc = 1
    sup.tick()
    clock[0] += 11
    assert sup.tick() == "gave_up" and len(procs) == 3
    assert any(a["severity"] == "critical" for a in store.unsent_alerts())
    sup.reset()
    assert sup.tick() == "child"


def test_supervisor_external_capture_is_only_watched(env):
    cfg, paths, store = env
    sup = CaptureSupervisor(store, cfg["supervisor"], paths.data_dir / "capture.lock",
                            paths.log_dir / "c.log", spawn=lambda: pytest.fail("spawned"),
                            lock_held=lambda _p: True)
    assert sup.tick() == "external"


# ── sentinel ─────────────────────────────────────────────────────────────────
def test_sentinel_whitelist_enforced():
    d = parse_diagnosis('{"chan_doan": "mất đăng nhập", "nguyen_nhan": ["token hết hạn"], '
                        '"lenh_de_xuat": "/reset agy", "ly_do": "sau khi login"}', "W1")
    assert d.command == "/reset agy" and d.causes == ["token hết hạn"]
    assert parse_diagnosis('{"lenh_de_xuat": "rm -rf C:/data"}', "W1").command == "none"
    assert parse_diagnosis('{"lenh_de_xuat": "/retry W2"}', "W1").command == "none"
    assert parse_diagnosis('{"lenh_de_xuat": "/retry W1"}', "W1").command == "/retry W1"
    assert parse_diagnosis("không phải JSON", None).command == "none"


def test_sentinel_failure_never_raises(env):
    cfg, paths, store = env

    def boom(_ctx):
        raise RuntimeError("agy offline")

    d = diagnose(store, br.Breakers(store, cfg["breaker"]), paths.log_dir, "W1", call=boom)
    assert d.command == "none" and "agy offline" in d.summary
    assert store.events(limit=1)[-1]["kind"] == "sentinel.diagnosis"


# ── DBOS: workflow bền chạy thật trên SQLite tạm, tách tiến trình ────────────
DBOS_SCRIPT = r"""
import sys, json
from pathlib import Path
sys.path.insert(0, {root!r})
from src.ops.config import load_config, resolve_paths
from src.ops.store import OpsStore
from src.ops.wave_flow import WaveSpec, WaveSteps
from src.ops import dbos_flow
from dbos import DBOS

class Steps(WaveSteps):
    def preflight(self, spec): return True, "", False
    def prepare(self, spec): return 3
    def analyze(self, spec, round_no):
        from src.ops.wave_flow import AnalyzeOutcome
        return AnalyzeOutcome("analyze", "ok", 3, 3, "OK")
    def finish(self, spec):
        from src.ops.procrun import StepResult
        return StepResult(0, "ok", 0.1, "ok", Path("x"))

cfg = load_config()
paths = resolve_paths(Path({data!r}))
store = OpsStore(paths.ops_db)
steps = Steps(store, cfg, paths, db_probe=lambda: (True, ""))
dbos_flow.init_dbos(paths)
dbos_flow.bind(steps, cfg)
DBOS.launch()
spec = WaveSpec("W7", "2026-10-01", "T1", "L1")
store.upsert_wave("W7", status="SENSED", workflow_id=spec.workflow_id)
wid = dbos_flow.start_wave(spec)
res = DBOS.retrieve_workflow(wid).get_result()
out = {{"result": res, "status": store.wave("W7")["status"]}}

# B7: step ném lỗi thì workflow chốt FAILED thay vì để đợt kẹt ở trạng thái đang chạy.
class Broken(Steps):
    def analyze(self, spec, round_no):
        raise RuntimeError("runner nổ")

dbos_flow.bind(Broken(store, cfg, paths, db_probe=lambda: (True, "")), cfg)
spec2 = WaveSpec("W8", "2026-10-01", "T1", "L1")
store.upsert_wave("W8", status="SENSED", workflow_id=spec2.workflow_id)
res2 = DBOS.retrieve_workflow(dbos_flow.start_wave(spec2)).get_result()
out["broken_result"] = res2
out["broken_status"] = store.wave("W8")["status"]
print(json.dumps(out, ensure_ascii=False))
DBOS.destroy()
"""


def test_dbos_workflow_runs_through_and_b7_step_error_fails_wave(tmp_path):
    script = tmp_path / "run_dbos.py"
    script.write_text(DBOS_SCRIPT.format(root=str(PROJECT_ROOT), data=str(tmp_path / "data")),
                      encoding="utf-8")
    proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                          encoding="utf-8", timeout=120, cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr[-2000:]
    import json as _json

    last = _json.loads(proc.stdout.strip().splitlines()[-1])
    assert last["result"] == "DONE" and last["status"] == "DONE"
    assert last["broken_result"] == "FAILED" and last["broken_status"] == "FAILED"
