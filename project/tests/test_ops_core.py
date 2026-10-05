"""Kiểm thử store, breaker, sensor, standing order, outbox và lệnh của tầng vận hành."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.ops import breakers as br
from src.ops import commands
from src.ops.config import load_config, resolve_paths
from src.ops.notify import drain_alerts
from src.ops.order import StandingOrder, demote, extend, load_order, save_order
from src.ops.probes import ProbeResult, apply_edges
from src.ops.sensor import SensorReading, decide, in_windows
from src.ops.store import VN_TZ, OpsStore, iso


@pytest.fixture
def env(tmp_path):
    cfg = load_config()
    paths = resolve_paths(tmp_path / "data")
    store = OpsStore(paths.ops_db, log_dir=paths.log_dir, dedup_minutes=30)
    return cfg, paths, store


# ── store ────────────────────────────────────────────────────────────────────
def test_emit_writes_db_and_jsonl(env):
    _, paths, store = env
    store.emit("wave.opened", "mở đợt", wave_id="W1", data={"n": 3})
    rows = store.events(limit=5)
    assert rows[-1]["kind"] == "wave.opened" and rows[-1]["wave_id"] == "W1"
    files = list(paths.log_dir.glob("*.jsonl"))
    assert files and "wave.opened" in files[0].read_text(encoding="utf-8")


def test_alert_dedup_counts_repeats(env):
    _, _, store = env
    first = store.alert("error", "mất mạng", dedup_key="k")
    second = store.alert("error", "mất mạng", dedup_key="k")
    assert first is not None and second is None
    rows = store.unsent_alerts()
    assert len(rows) == 1 and rows[0]["repeats"] == 2


def test_active_wave_and_parked(env):
    _, _, store = env
    store.upsert_wave("W1", status="ANALYZING", provider="agy")
    assert store.active_wave()["wave_id"] == "W1"
    store.upsert_wave("W1", status="PARKED", resume_on_breaker=1)
    assert store.active_wave() is None
    assert [w["wave_id"] for w in store.parked_for_breaker()] == ["W1"]


# ── breaker ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text,cls", [
    ("HTTP 401 Unauthorized", br.AUTH),
    ("Error: please log in again", br.AUTH),
    ("429 RESOURCE_EXHAUSTED", br.QUOTA),
    ("getaddrinfo failed", br.NETWORK),
    ("503 Service Unavailable", br.NETWORK),
    ("Quá thời gian thực thi 600 giây.", br.TIMEOUT),
    ("Bóc tách JSON thất bại: Expecting value", br.EMPTY),
    ("Lỗi đọc tệp task.json", br.FATAL),
])
def test_classify(text, cls):
    assert br.classify(text) == cls


def test_classify_batch_statuses():
    assert br.classify_batch("OK", "") == br.OK
    assert br.classify_batch("PARTIAL", "") == br.OK
    assert br.classify_batch("QUOTA", "") == br.QUOTA
    assert br.classify_batch("RETRYABLE", "503") == br.NETWORK
    assert br.classify_batch("SOFT_FAIL", "") == br.EMPTY
    assert br.classify_batch("FATAL", "Tiến trình agy thất bại: not logged in") == br.AUTH
    assert br.worst([br.OK, br.TIMEOUT, br.QUOTA]) == br.QUOTA


def test_network_trips_after_threshold(env):
    cfg, _, store = env
    b = br.Breakers(store, cfg["breaker"])
    assert b.record("agy", br.NETWORK) is None
    assert b.record("agy", br.NETWORK) is None
    assert b.record("agy", br.NETWORK) == "opened"
    allowed, st = b.allow("agy")
    assert not allowed and st.reason == br.NETWORK and st.reopen_at


def test_quota_opens_immediately_and_auth_waits_for_human(env):
    cfg, _, store = env
    b = br.Breakers(store, cfg["breaker"])
    assert b.record("agy", br.QUOTA) == "opened"
    assert b.get("agy").reopen_at is not None
    assert b.record("openrouter", br.AUTH) == "opened"
    assert b.get("openrouter").reopen_at is None
    assert not b.allow("openrouter")[0]
    b.reset("openrouter")
    assert b.allow("openrouter")[0]


def test_half_open_success_closes_and_failure_reopens(env):
    cfg, _, store = env
    b = br.Breakers(store, cfg["breaker"])
    b.record("agy", br.QUOTA)
    with store.conn() as c:
        c.execute("UPDATE provider_breakers SET reopen_at = ? WHERE provider = 'agy'",
                  (iso(datetime.now(VN_TZ) - timedelta(minutes=1)),))
    allowed, st = b.allow("agy")
    assert allowed and st.state == "HALF_OPEN"
    assert b.record("agy", br.TIMEOUT) == "opened"
    with store.conn() as c:
        c.execute("UPDATE provider_breakers SET reopen_at = ? WHERE provider = 'agy'",
                  (iso(datetime.now(VN_TZ) - timedelta(minutes=1)),))
    b.allow("agy")
    assert b.record("agy", br.OK) == "closed"
    assert b.get("agy").state == "CLOSED"


def test_fatal_does_not_touch_breaker(env):
    cfg, _, store = env
    b = br.Breakers(store, cfg["breaker"])
    for _ in range(5):
        b.record("agy", br.FATAL)
    assert b.get("agy").state == "CLOSED"


# ── sensor ───────────────────────────────────────────────────────────────────
def _reading(n: int, age_min: float | None, now: datetime) -> SensorReading:
    r = SensorReading(per_date=[(now.date().isoformat(), n)])
    if age_min is not None:
        r.oldest_fetched_at = now - timedelta(minutes=age_min)
    return r


def test_decide_rules():
    cfg = load_config()["sensor"]
    noon = datetime(2026, 10, 1, 10, 0, tzinfo=VN_TZ)
    night = datetime(2026, 10, 1, 23, 30, tzinfo=VN_TZ)
    assert decide(_reading(0, None, noon), cfg, now=noon)[0] is False
    assert decide(_reading(120, 5, noon), cfg, now=noon)[1] == "T1"
    assert decide(_reading(30, 120, noon), cfg, now=noon)[1] == "T2"
    assert decide(_reading(30, 120, night), cfg, now=night)[0] is False
    flush = datetime(2026, 10, 1, 12, 20, tzinfo=VN_TZ)
    assert decide(_reading(5, 10, flush), cfg, now=flush)[1] == "T3"
    assert decide(_reading(5, 10, noon), cfg, now=noon, force=True)[1] == "manual"
    assert decide(_reading(5, 10, noon), cfg, now=noon)[0] is False


def test_target_date_is_oldest_with_pending():
    r = SensorReading(per_date=[("2026-09-30", 0), ("2026-10-01", 7)])
    assert r.target_date == "2026-10-01" and r.total == 7
    r = SensorReading(per_date=[("2026-09-30", 3), ("2026-10-01", 7)])
    assert r.target_date == "2026-09-30"


def test_in_windows():
    assert in_windows(datetime(2026, 1, 1, 7, 20), ["07:15-07:45"]) == "07:15-07:45"
    assert in_windows(datetime(2026, 1, 1, 8, 0), ["07:15-07:45"]) is None


# ── standing order ───────────────────────────────────────────────────────────
def test_order_roundtrip_and_expiry(tmp_path):
    p = tmp_path / "order.yaml"
    assert load_order(p).effective_level() == "L0"
    o = extend(StandingOrder(level="L1", failover="ask"), 30, 7)
    assert date.fromisoformat(o.valid_until) == date.today() + timedelta(days=7)
    save_order(p, o)
    back = load_order(p)
    assert back.effective_level() == "L1" and back.failover == "ask"
    back.valid_until = (date.today() - timedelta(days=1)).isoformat()
    assert back.effective_level() == "L0"
    assert demote("L1") == "L0" and demote("L0") == "L0"


def test_legacy_l2_l3_order_reads_as_l1(tmp_path):
    p = tmp_path / "order.yaml"
    p.write_text(f"level: L3\nvalid_until: {date.today().isoformat()}\n", encoding="utf-8")
    assert load_order(p).effective_level() == "L1"


def test_order_file_stays_readable_by_article_tick(tmp_path, monkeypatch):
    import scripts.article_tick as tick

    p = tmp_path / "order.yaml"
    save_order(p, extend(StandingOrder(level="L1"), 3, 7))
    monkeypatch.setattr(tick, "STANDING_ORDER_PATH", p)
    data = tick.load_standing_order()
    assert data["level"] == "L1" and int(data["max_limit"]) == 100


# ── outbox ───────────────────────────────────────────────────────────────────
class FakeTelegram:
    def __init__(self, fail: bool = False):
        self.sent: list[tuple] = []
        self.fail = fail

    def send(self, chat, text, buttons=None, silent=False):
        if self.fail:
            raise RuntimeError("network down")
        self.sent.append((chat, text, buttons, silent))
        return 1


def test_drain_alerts_marks_sent_and_keeps_failures(env):
    _, _, store = env
    store.alert("critical", "DB không ghi được", buttons=[[("Chẩn đoán", "/diagnose")]])
    bad = FakeTelegram(fail=True)
    assert drain_alerts(store, bad, ["1"]) == (0, 1)
    assert len(store.unsent_alerts()) == 1
    good = FakeTelegram()
    assert drain_alerts(store, good, ["1"]) == (1, 0)
    chat, text, buttons, silent = good.sent[0]
    assert text.startswith("[KHẨN]") and buttons == [[("Chẩn đoán", "/diagnose")]] and not silent
    assert not store.unsent_alerts()


def test_drain_expires_stale_alerts(env):
    _, _, store = env
    store.alert("error", "cũ")
    with store.conn() as c:
        c.execute("UPDATE ops_alerts SET created_at = ?",
                  (iso(datetime.now(VN_TZ) - timedelta(hours=10)),))
    store.alert("error", "mới")
    client = FakeTelegram()
    assert drain_alerts(store, client, ["1"]) == (1, 0)
    assert "mới" in client.sent[0][1] and not store.unsent_alerts()


def test_drain_without_telegram_keeps_outbox(env):
    _, _, store = env
    store.alert("info", "x")
    assert drain_alerts(store, None, []) == (0, 0)
    assert len(store.unsent_alerts()) == 1


# ── probe theo cạnh ──────────────────────────────────────────────────────────
def test_probe_edges_alert_once_and_on_recovery(env):
    _, _, store = env
    apply_edges(store, [ProbeResult("capture", True, "error", "ok")])
    assert not store.unsent_alerts()
    apply_edges(store, [ProbeResult("capture", False, "error", "đứng 45 phút")])
    apply_edges(store, [ProbeResult("capture", False, "error", "đứng 47 phút")])
    assert len(store.unsent_alerts()) == 1
    apply_edges(store, [ProbeResult("capture", True, "error", "tươi")])
    texts = [r["text"] for r in store.unsent_alerts()]
    assert any("đã hồi phục" in t for t in texts)


# ── lệnh ─────────────────────────────────────────────────────────────────────
class FakeController:
    def __init__(self, cfg, paths, store):
        self.cfg, self.paths, self.store = cfg, paths, store
        self.breakers = br.Breakers(store, cfg["breaker"])
        self.calls: list[tuple] = []

    def request_wave(self):
        self.calls.append(("run",))
        return "ok run"

    def retry_wave(self, wave_id):
        self.calls.append(("retry", wave_id))
        return "ok retry"

    def diagnose_async(self, wave_id):
        self.calls.append(("diagnose", wave_id))
        return "ok diag"

    def capture_restart(self):
        return "ok capture"


def test_commands_pause_stop_level_reset(env):
    cfg, paths, store = env
    ctl = FakeController(cfg, paths, store)
    commands.execute("/pause", ctl)
    assert store.get_state("paused") == "1"
    commands.execute("/resume", ctl)
    assert store.get_state("paused") is None

    r = commands.execute("/stop", ctl)
    assert not paths.kill_switch.exists() and r.buttons
    store.upsert_wave("W9", status="ANALYZING")
    commands.execute("/stop confirm", ctl)
    assert paths.kill_switch.exists() and store.get_state("cancel:W9") == "1"
    commands.execute("/unstop", ctl)
    assert not paths.kill_switch.exists()

    r = commands.execute("/level L1", ctl)
    assert not load_order(paths.standing_order).exists and r.buttons
    commands.execute("/level L1 confirm", ctl)
    assert load_order(paths.standing_order).effective_level() == "L1"
    commands.execute("/failover ask", ctl)
    assert load_order(paths.standing_order).failover == "ask"

    ctl.breakers.record("agy", br.AUTH)
    commands.execute("/reset agy", ctl)
    assert ctl.breakers.get("agy").state == "CLOSED"

    assert "Không hiểu lệnh" in commands.execute("/approve W9", ctl).text
    commands.execute("/retry W9", ctl)
    assert ("retry", "W9") in ctl.calls
    kinds = [e["kind"] for e in store.events(limit=50)]
    assert kinds.count("human.command") >= 8


def test_commands_read_only_not_audited_and_unknown_help(env):
    cfg, paths, store = env
    ctl = FakeController(cfg, paths, store)
    assert "Daemon" in commands.execute("/status", ctl).text
    assert "Lệnh vận hành" in commands.execute("/khongco", ctl).text
    assert not [e for e in store.events(limit=50) if e["kind"] == "human.command"
                and "/status" in e["message"]]


def test_command_without_slash(env):
    cfg, paths, store = env
    ctl = FakeController(cfg, paths, store)
    commands.execute("pause", ctl)
    assert store.get_state("paused") == "1"


def test_order_extend_from_l0_starts_l1(env):
    cfg, paths, store = env
    ctl = FakeController(cfg, paths, store)
    assert commands.execute("/order extend 3", ctl).buttons
    commands.execute("/order extend 3 confirm", ctl)
    o = load_order(paths.standing_order)
    assert o.effective_level() == "L1"
    assert date.fromisoformat(o.valid_until) == date.today() + timedelta(days=3)


# ── giao hàng tự động sau DONE ─────────────────────────────────────────────
def _deliver_steps(env, ok=True):
    from pathlib import Path as _P

    from src.ops.procrun import StepResult
    from src.ops.wave_flow import WaveSteps

    cfg, paths, store = env
    calls = []

    def fake_executor(cmd, **kw):
        calls.append(cmd)
        return StepResult(returncode=0 if ok else 1, outcome="ok" if ok else "failed",
                          duration_s=1.0, tail="", log_path=_P(str(kw.get("log_path") or "x")))

    steps = WaveSteps(store, cfg, paths, executor=fake_executor)
    return steps, calls


def test_finalize_done_runs_deliver_per_date(env):
    from src.ops.wave_flow import WaveSpec

    steps, calls = _deliver_steps(env, ok=True)
    spec = WaveSpec(wave_id="WD1", target_date="2026-10-02", trigger="T1", level="L1")
    assert steps.finalize(spec, "DONE", "xong", counts_as_failure=False) == "DONE"
    assert any(any("write_user_output.py" in part for part in c) and "2026-10-02" in c
               for c in calls)
    kinds = [e["kind"] for e in steps.store.events(limit=20)]
    assert "wave.delivered" in kinds


def test_finalize_done_deliver_failure_keeps_done(env):
    from src.ops.wave_flow import WaveSpec

    steps, _ = _deliver_steps(env, ok=False)
    spec = WaveSpec(wave_id="WD2", target_date="2026-10-02", trigger="T1", level="L1")
    assert steps.finalize(spec, "DONE", "xong", counts_as_failure=False) == "DONE"
    kinds = [e["kind"] for e in steps.store.events(limit=20)]
    assert "wave.deliver_failed" in kinds
    assert steps.store.unsent_alerts()


def test_finalize_not_done_skips_deliver(env):
    from src.ops.wave_flow import WaveSpec

    steps, calls = _deliver_steps(env, ok=True)
    spec = WaveSpec(wave_id="WD3", target_date="2026-10-02", trigger="T1", level="L1")
    assert steps.finalize(spec, "FAILED", "hong", counts_as_failure=True) == "FAILED"
    assert steps.finalize(spec, "DONE", "rong", counts_as_failure=False, clean=False) == "DONE"
    assert calls == []
