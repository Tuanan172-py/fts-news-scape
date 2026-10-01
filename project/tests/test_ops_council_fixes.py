"""Kiểm thử hồi quy cho các mục Chặn của hội đồng 2026-10-01 (B2–B7) và quyết định D1', D9, D10."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
import requests

from src.ops import commands
from src.ops.config import load_config, resolve_paths
from src.ops.notify import TelegramClient
from src.ops.procrun import StepResult
from src.ops.redact import redact
from src.ops.store import OpsStore, iso, now_vn
from src.ops.wave_flow import WaveSpec, WaveSteps

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FAKE_TOKEN = "123456789:AAH" + "x" * 32


@pytest.fixture
def env(tmp_path):
    cfg = load_config()
    paths = resolve_paths(tmp_path / "data")
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    store = OpsStore(paths.ops_db, log_dir=paths.log_dir)
    return cfg, paths, store


# ── B2: đợt chưa xong giữ chỗ bài của nó ─────────────────────────────────────
def test_b2_parked_and_failed_waves_keep_articles_reserved(env):
    _, _, store = env
    store.upsert_wave("W1", status="ANALYZING")
    store.record_wave_articles("W1", ["a1", "a2"])
    assert store.reserved_article_ids() == {"a1", "a2"}
    for status in ("PARKED", "FAILED"):
        store.upsert_wave("W1", status=status)
        assert store.reserved_article_ids() == {"a1", "a2"}
    store.upsert_wave("W1", status="CANCELLED")
    assert store.reserved_article_ids() == set()


def _candidate_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE articles (url_title_hash TEXT, title TEXT, published_at TEXT,
                               source_domain TEXT, content_text TEXT, fetched_at TEXT);
        CREATE TABLE work_items (article_id TEXT, package_path TEXT);
        CREATE TABLE l1_outputs (article_id TEXT, dod_pass INTEGER, l1_source TEXT);
    """)
    body = "x" * 200
    for i in range(5):
        conn.execute("INSERT INTO articles VALUES (?,?,?,?,?,?)",
                     (f"a{i}", f"t{i}", "2026-10-01T08:00:00", "d", body,
                      "2026-10-01T08:00:00+07:00"))
    conn.execute("INSERT INTO l1_outputs VALUES ('a4', 1, 'agent')")
    conn.commit()
    conn.close()


def test_b2_load_candidates_excludes_before_limit_on_read_only_connection(tmp_path):
    from scripts.article_pack import load_candidates

    db = tmp_path / "m.db"
    _candidate_db(db)
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = load_candidates(conn, date="2026-10-01", limit=2, only_pending=True,
                           exclude={"a0", "a1"}, with_content=False)
    ids = sorted(r["article_id"] for r in rows)
    assert ids == ["a2", "a3"] and "content_text" not in rows[0].keys()
    conn.close()


def test_b2_sensor_does_not_count_reserved_articles(tmp_path):
    from src.ops.sensor import read_pending

    db = tmp_path / "m.db"
    _candidate_db(db)
    now = now_vn().replace(year=2026, month=10, day=1, hour=12)
    r = read_pending(db, 0, now=now, exclude={"a0"})
    assert r.total == 3


# ── B3: tiến trình con chết theo daemon ──────────────────────────────────────
@pytest.mark.skipif(os.name != "nt", reason="Job Object chỉ có trên Windows")
def test_b3_children_die_when_daemon_process_dies(tmp_path):
    pid_file = tmp_path / "grandchild.pid"
    pid_posix = pid_file.as_posix()
    owner = textwrap.dedent(f"""
        import os, subprocess, sys, time
        sys.path.insert(0, {str(PROJECT_ROOT)!r})
        from src.ops.procrun import popen_in_daemon_job
        code = ("import os, subprocess, sys, time;"
                "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']);"
                "open({pid_posix!r}, 'w').write(str(p.pid)); time.sleep(120)")
        child, attached = popen_in_daemon_job([sys.executable, '-c', code])
        assert attached
        for _ in range(100):
            if os.path.exists({pid_posix!r}):
                break
            time.sleep(0.1)
        os._exit(0)
    """)
    subprocess.run([sys.executable, "-c", owner], timeout=60, check=True)
    import psutil

    gpid = int(pid_file.read_text())
    for _ in range(50):
        if not psutil.pid_exists(gpid):
            break
        time.sleep(0.2)
    alive = psutil.pid_exists(gpid)
    if alive:
        psutil.Process(gpid).kill()
    assert not alive, "tiến trình cháu sống sót sau khi daemon chết"


# ── B4: bài hết lượt thử không được đóng gói lại ─────────────────────────────
def test_b4_article_exhausts_after_max_attempts(env):
    _, _, store = env
    store.upsert_wave("W1", status="DONE")
    store.record_wave_articles("W1", ["bad", "ok"])
    store.record_wave_articles("W1", ["bad", "ok"])  # chạy lại sau crash: không tăng
    assert store.exhausted_article_ids(2) == set()
    store.upsert_wave("W2", status="DONE")
    store.record_wave_articles("W2", ["bad"])
    assert store.exhausted_article_ids(2) == {"bad"}
    assert store.excluded_article_ids(2) == {"bad"}


def test_b4_prepare_passes_exclusions_and_records_articles(env, tmp_path):
    cfg, paths, store = env
    task_dir = tmp_path / "t"
    task_dir.mkdir()
    store.upsert_wave("W0", status="PARKED")
    store.record_wave_articles("W0", ["held"])
    seen = {}

    def fake_exec(cmd, **kw):
        seen["cmd"] = cmd
        (task_dir / "wave_W1.json").write_text('{"articles": 2}', encoding="utf-8")
        (task_dir / "article_W1_01.map.json").write_text(
            '{"index": {"0": "x1", "1": "x2"}}', encoding="utf-8")
        return StepResult(0, "ok", 0.1, "", kw["log_path"])

    steps = WaveSteps(store, cfg, paths, executor=fake_exec, task_dir=task_dir,
                      out_dir=tmp_path / "o", db_probe=lambda: (True, ""))
    store.upsert_wave("W1", status="SENSED")
    assert steps.prepare(WaveSpec("W1", "2026-10-01", "T1", "L1")) == 2
    excl = Path(seen["cmd"][seen["cmd"].index("--exclude-file") + 1])
    assert excl.read_text(encoding="utf-8").split() == ["held"]
    assert store.reserved_article_ids() == {"held", "x1", "x2"}


def test_b4_prepare_with_nothing_left_is_empty_not_failure(env, tmp_path):
    cfg, paths, store = env

    def fake_exec(cmd, **kw):
        return StepResult(2, "failed", 0.1, "Không có bài nào thoả điều kiện.", kw["log_path"])

    steps = WaveSteps(store, cfg, paths, executor=fake_exec, task_dir=tmp_path / "t",
                      out_dir=tmp_path / "o", db_probe=lambda: (True, ""))
    assert steps.prepare(WaveSpec("W1", "2026-10-01", "T1", "L1")) == 0


# ── B5: bí mật không lọt vào sự kiện, cảnh báo, lỗi gửi ──────────────────────
def test_b5_redact_patterns():
    text = (f"POST https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage "
            "https://hc-ping.com/1f2e3d4c-aaaa-bbbb-cccc-1234567890ab "
            "Bearer sk-or-v1-abcdefghijklmnopqrstuvwxyz")
    out = redact(text)
    assert FAKE_TOKEN not in out and "1f2e3d4c" not in out and "abcdefghijklmnop" not in out
    assert "api.telegram.org/bot***" in out


def test_b5_store_masks_events_alerts_and_send_errors(env):
    _, paths, store = env
    store.emit("telegram.poll_error", f"lỗi url /bot{FAKE_TOKEN}/getUpdates",
               data={"trace": f"bot{FAKE_TOKEN}"})
    aid = store.alert("error", f"gửi lỗi bot{FAKE_TOKEN}")
    store.mark_alert(aid, sent=False, error=f"ConnectionError bot{FAKE_TOKEN}")
    dump = "".join(f.read_text(encoding="utf-8") for f in paths.log_dir.glob("*.jsonl"))
    with store.conn() as c:
        rows = [tuple(r) for r in c.execute("SELECT * FROM ops_events")]
        rows += [tuple(r) for r in c.execute("SELECT * FROM ops_alerts")]
    assert FAKE_TOKEN not in dump and FAKE_TOKEN not in repr(rows)


def test_b5_telegram_network_error_hides_token():
    class Boom:
        def post(self, url, **kw):
            raise requests.ConnectionError(f"HTTPSConnectionPool url: {url}")

    client = TelegramClient(FAKE_TOKEN, session=Boom())
    with pytest.raises(RuntimeError) as ei:
        client.send("1", "x")
    assert FAKE_TOKEN not in str(ei.value)


# ── B6: bước nạp DB không bị cắt ngang bởi lệnh dừng ─────────────────────────
def test_b6_finish_runs_without_stop_hook(env, tmp_path):
    cfg, paths, store = env
    seen = {}

    def fake_exec(cmd, **kw):
        seen.update(kw)
        return StepResult(0, "ok", 0.1, "", kw["log_path"])

    steps = WaveSteps(store, cfg, paths, executor=fake_exec, task_dir=tmp_path / "t",
                      out_dir=tmp_path / "o", db_probe=lambda: (True, ""))
    paths.kill_switch.write_text("x", encoding="utf-8")
    assert steps.finish(WaveSpec("W1", "2026-10-01", "T1", "L1")).ok
    assert seen["stop_fn"] is None and seen["deadline_s"] == 30 * 60


def test_b6_agy_ledger_rerun_replaces_row(tmp_path, monkeypatch):
    import scripts.token_ledger as tl

    out_dir = tmp_path / "data" / "agent_outputs_article"
    out_dir.mkdir(parents=True)
    (out_dir / "article_WX_01.meta.json").write_text(
        '{"usage": {"input_tokens": 10, "output_tokens": 5}}', encoding="utf-8")
    monkeypatch.setattr(tl, "__file__", str(tmp_path / "scripts" / "token_ledger.py"))
    db = str(tmp_path / "h.db")
    ns = tl.argparse.Namespace(db=db, wave="WX", batch=None, items=1, since=0,
                               window_min=60, workers_only=True, source="agy",
                               est_miss=None, est_out=None)
    assert tl.cmd_append(ns) == 0 and tl.cmd_append(ns) == 0
    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM token_ledger WHERE wave='WX'").fetchone()[0]
    conn.close()
    assert n == 1


# ── B7: đợt mất workflow được đối chiếu ở mỗi nhịp, không chỉ lúc khởi động ──
def test_b7_reconcile_marks_lost_workflow_failed(env, monkeypatch):
    import dbos

    from src.ops.daemon import OpsDaemon

    _, _, store = env
    store.upsert_wave("W5", status="ANALYZING", workflow_id="wave-W5")

    class Status:
        status = "ERROR"

    monkeypatch.setattr(dbos.DBOS, "get_workflow_status", staticmethod(lambda _w: Status()))
    fake = type("D", (), {"store": store})()
    OpsDaemon.reconcile(fake)
    assert store.wave("W5")["status"] == "FAILED" and store.active_wave() is None
    assert any("/cancel W5" in (a["buttons_json"] or "") for a in store.unsent_alerts())


# ── D1' / R2: chỉ chat riêng của đúng người ──────────────────────────────────
def test_r2_telegram_accepts_only_private_chat_from_whitelisted_sender():
    from src.ops.daemon import OpsDaemon

    fake = type("D", (), {"chat_ids": ["42"]})()
    ok = OpsDaemon._authorized
    assert ok(fake, {"id": 42, "type": "private"}, {"id": 42})
    assert not ok(fake, {"id": 42, "type": "group"}, {"id": 42})
    assert not ok(fake, {"id": 42, "type": "private"}, {"id": 7})
    assert not ok(fake, {"id": 7, "type": "private"}, {"id": 7})


def test_r2_elevating_commands_need_confirmation(env):
    cfg, paths, store = env

    class Ctl:
        pass

    ctl = Ctl()
    ctl.cfg, ctl.paths, ctl.store = cfg, paths, store
    from src.ops.breakers import Breakers

    ctl.breakers = Breakers(store, cfg["breaker"])
    for cmd in ("/level L1", "/provider openrouter", "/failover auto", "/order extend 7"):
        r = commands.execute(cmd, ctl)
        assert r.buttons and r.buttons[0][0][1] == f"{cmd} confirm", cmd
    assert not commands.execute("/level L0", ctl).buttons
    commands.execute("/provider openrouter confirm", ctl)
    from src.ops.order import load_order

    assert load_order(paths.standing_order).provider == "openrouter"


def test_cancel_parked_wave_releases_articles(env):
    cfg, paths, store = env
    store.upsert_wave("W1", status="PARKED")
    store.record_wave_articles("W1", ["a"])
    ctl = type("C", (), {"cfg": cfg, "paths": paths, "store": store, "breakers": None})()
    commands.execute("/cancel W1", ctl)
    assert store.wave("W1")["status"] == "CANCELLED" and store.reserved_article_ids() == set()


# ── D9: watchdog chỉ báo sau hai lần kiểm liên tiếp thấy nhịp tim cũ ─────────
def test_d9_watchdog_alerts_once_after_two_stale_checks(tmp_path, monkeypatch):
    import scripts.ops_daemon as cli

    monkeypatch.setenv("MONOCLE_DATA_DIR", str(tmp_path / "data"))
    for k in ("NEWS_SCAPE_TG_TOKEN", "NEWS_SCAPE_TG_CHAT_IDS", "NEWS_SCAPE_HC_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(cli, "_redirect_if_windowless", lambda _d: None)
    paths = resolve_paths()
    store = OpsStore(paths.ops_db)
    store.set_state("heartbeat_at", iso(now_vn().replace(year=2026, month=1, day=1)))

    def dead_events():
        return [e for e in store.events(limit=50) if e["kind"] == "watchdog.daemon_dead"]

    cli.cmd_watchdog(None)
    assert not dead_events()
    cli.cmd_watchdog(None)
    cli.cmd_watchdog(None)
    assert len(dead_events()) == 1
    store.set_state("heartbeat_at", iso())
    cli.cmd_watchdog(None)
    assert store.get_state("watchdog:alerted") is None


# ── Đợt thật đầu tiên: Task Scheduler không bung %LOCALAPPDATA% trong PATH ───
def test_resolve_agy_expands_unexpanded_path_entries(tmp_path, monkeypatch):
    from src.agent.agy_runner import resolve_agy

    bin_dir = tmp_path / "Local" / "agy" / "bin"
    bin_dir.mkdir(parents=True)
    exe = bin_dir / ("agy.exe" if os.name == "nt" else "agy")
    exe.write_bytes(b"")
    exe.chmod(0o755)
    monkeypatch.delenv("AGY_BIN", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("PATH", "%LOCALAPPDATA%" + os.sep + "agy" + os.sep + "bin")
    monkeypatch.setattr("shutil.which", lambda name, path=None: (
        str(exe) if path and Path(path) == bin_dir else None))
    assert Path(resolve_agy()) == exe
