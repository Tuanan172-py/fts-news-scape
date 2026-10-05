"""Kiểm thử P1–P4 của US-031: tầng đọc giám sát, Phòng điều khiển, bản tin, đề xuất, mandate."""

from __future__ import annotations

import http.client
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from src.ops import commands, improve, mandate, reports
from src.ops import supervision as sv
from src.ops.breakers import Breakers
from src.ops.config import load_config, resolve_paths
from src.ops.control_room import ControlRoom
from src.ops.order import StandingOrder, extend, load_order, save_order
from src.ops.store import OpsStore, iso, now_vn
from src.ops.trace import Tracer


@pytest.fixture
def env(tmp_path):
    cfg = load_config()
    paths = resolve_paths(tmp_path / "data")
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    store = OpsStore(paths.ops_db, log_dir=paths.log_dir)
    return cfg, paths, store, Breakers(store, cfg["breaker"])


def seed_wave(store, wave_id, *, first=56, total=100, repair_tokens=84_710, main_tokens=119_352,
              hours_ago=0, status="DONE", latency=40.0):
    """Gieo một đợt có vết giống đợt thật: analyze nhận một phần, repair lấy nốt."""
    opened = now_vn() - timedelta(hours=hours_ago)
    store.upsert_wave(wave_id, status=status, n_articles=total, trigger="manual", level="L1",
                      provider="agy", target_date="2026-10-01", opened_at=iso(opened),
                      finished_at=iso(opened + timedelta(seconds=114)), reason="seed")
    tr = Tracer(store.path, wave_id)
    root = f"{wave_id}.a0"
    tr.begin(f"wave-{wave_id}", "workflow", "master-orchestrator", span_id=root, parent_id=None)
    for step, recv, tok, actor in (("analyze", first, main_tokens, "article-processor"),
                                   ("repair1", total, repair_tokens, "article-processor")):
        sid = f"{root}.{step}"
        tr.begin(step, "step", actor, span_id=sid, parent_id=root)
        tr.finish(sid, "ok", received=recv, total=total)
        for k in range(2):
            aid = f"{sid}/b{k}"
            tr.begin(f"lô b{k}", "agent", "article-processor", span_id=aid, parent_id=sid)
            tr.finish(aid, "ok", usage={"total_tokens": tok // 2, "input_tokens": tok // 3,
                                        "cache_read_tokens": 0},
                      latency_s=latency, tool_invoked=False, denied_actions=False)
    tr.finish(root, "ok")


# ── tầng đọc ─────────────────────────────────────────────────────────────────
def test_registry_exposes_agents_with_skill_and_tools():
    reg = sv.registry()
    assert reg["article-processor"]["class"] == "cognitive"
    assert reg["article-processor"]["tools_allowed"] == []
    assert reg["master-orchestrator"]["class"] == "conductor"


def test_map_nodes_follow_registry_and_runtime_state(env):
    cfg, paths, store, br = env
    seed_wave(store, "W1", status="DONE")
    Tracer(store.path, "W2").begin("lô x", "agent", "article-processor", span_id="W2.run")
    m = sv.build_map(store, cfg, paths, br)
    by = {n["id"]: n for n in m["nodes"]}
    assert by["article-processor"]["state"] == "run" and by["article-processor"]["tools"] == 0
    assert by["article-processor"]["stats"]["tokens"] > 0
    assert by["article-packer"]["state"] == "idle"
    assert "story-dedup-clusterer" not in by                          # retired không hiện
    assert "l1-router" not in by                                      # retired không hiện
    assert m["chain"][:4] == ["scraper-orchestrator", "article-packer", "article-processor",
                              "article-expander"]
    xs = [(by[a]["x"], by[a]["x"] + by[a]["w"]) for a in m["chain"]]
    assert all(b0 >= a1 for (_, a1), (b0, _) in zip(xs, xs[1:]))      # không chồng nhau
    assert xs[-1][1] <= m["width"]


def test_waves_summary_computes_yield_and_repair_share(env):
    _, _, store, _ = env
    seed_wave(store, "W1")
    w = sv.waves(store)[0]
    assert w["first_pass_yield"] == 0.56 and w["tokens"] == 204_062
    assert w["repair_tokens"] == 84_710 and w["repair_share"] == pytest.approx(0.415, abs=0.001)
    assert w["duration_s"] == 114


def test_trace_offsets_and_unknown_wave(env):
    _, _, store, _ = env
    seed_wave(store, "W1")
    tr = sv.trace_of(store, "W1")
    assert {s["kind"] for s in tr["spans"]} == {"workflow", "step", "agent"}
    assert all(s["offset_ms"] >= 0 and s["duration_ms"] >= 0 for s in tr["spans"])
    assert sv.trace_of(store, "NOPE") == {"wave_id": "NOPE", "spans": [], "duration_ms": 0}


def test_agent_card_has_spec_trend_and_none_for_unknown(env):
    _, _, store, _ = env
    seed_wave(store, "W1")
    card = sv.agent_card(store, "article-processor")
    assert card["spec"]["tools_allowed"] == [] and card["spec"]["skill"].endswith("SKILL.md")
    assert card["trend"][0]["spans"] == 6 and card["trend"][0]["avg_latency_s"] == 40.0  # 2 bước + 4 lô
    assert card["violations"] == []
    assert sv.agent_card(store, "khong-co") is None


def test_anomalies_need_enough_waves_and_flag_outliers(env):
    _, _, store, _ = env
    for i in range(5):
        seed_wave(store, f"W{i}", first=56 + (i % 2), hours_ago=10 - i)
    assert sv.anomalies(store) == []                                   # mới 5 đợt: chưa đủ so sánh
    for i in range(5, 7):
        seed_wave(store, f"W{i}", first=56 + (i % 2), hours_ago=10 - i)
    seed_wave(store, "W9", first=5, hours_ago=0)                       # đợt gần nhất lệch hẳn
    metrics = [a["metric"] for a in sv.anomalies(store)]
    assert "first_pass_yield" in metrics


# ── Phòng điều khiển qua HTTP ────────────────────────────────────────────────
def _get(port, path, host=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": host} if host else {}
    h.update(headers or {})
    conn.request("GET", path, headers=h)
    r = conn.getresponse()
    return r.status, r.read().decode("utf-8")


def _post(port, path, token=None, host=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": host} if host else {}
    if token:
        h["X-CR-Token"] = token
    conn.request("POST", path, headers=h)
    r = conn.getresponse()
    return r.status, json.loads(r.read().decode("utf-8"))


@pytest.fixture
def room(env):
    cfg, paths, store, br = env
    calls = []

    def fake_harness(*args):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    cr = ControlRoom(store, cfg, paths, br, port=0, harness=fake_harness)
    assert cr.start()
    yield cr, store, calls
    cr.stop()


def test_control_room_serves_page_with_token_and_json(room):
    cr, store, _ = room
    seed_wave(store, "W1")
    code, html = _get(cr.port, "/")
    assert code == 200 and cr.token in html and "__CR_TOKEN__" not in html
    assert "Phòng điều khiển" in html
    for path in ("/api/state", "/api/map", "/api/waves", "/api/trace/W1", "/api/agents",
                 "/api/agent/article-processor", "/api/incidents", "/api/kpi", "/api/improvements"):
        code, body = _get(cr.port, path)
        assert code == 200, path
        json.loads(body)
    assert _get(cr.port, "/api/agent/khong-co")[0] == 404
    assert _get(cr.port, "/api/khong-co")[0] == 404


def test_control_room_rejects_foreign_host_and_unauthenticated_post(room):
    cr, store, calls = room
    assert _get(cr.port, "/api/state", host="evil.example.com")[0] == 403        # DNS rebinding
    with store.conn() as c:
        c.execute("INSERT INTO ops_proposals(created_at, dedup_key, kind, title, impact) "
                  "VALUES (?,?,?,?,?)", (iso(), "k", "yield", "Đề xuất thử", 1))
    assert _post(cr.port, "/api/improvements/1/reject")[0] == 403                # thiếu mã
    assert _post(cr.port, "/api/improvements/1/reject", token="sai")[0] == 403
    assert _post(cr.port, "/api/improvements/1/reject", token=cr.token, host="evil.com")[0] == 403
    assert sv.proposals(store, "open")[0]["status"] == "open" and calls == []


def test_control_room_proposal_decisions_via_post(room):
    cr, store, calls = room
    with store.conn() as c:
        for i in (1, 2):
            c.execute("INSERT INTO ops_proposals(created_at, dedup_key, kind, title, impact) "
                      "VALUES (?,?,?,?,?)", (iso(), f"k{i}", "yield", f"Đề xuất {i}", i))
    code, res = _post(cr.port, "/api/improvements/1/open_story", token=cr.token)
    assert code == 200 and res["story_id"] == "US-IMP-001"
    assert [c[0] for c in calls] == ["intake", "story"]                          # chỉ Mở story vào harness
    assert _post(cr.port, "/api/improvements/2/defer", token=cr.token)[0] == 200
    assert _post(cr.port, "/api/improvements/2/defer", token=cr.token)[0] == 409  # không quyết hai lần
    by_id = {p["id"]: p["status"] for p in sv.proposals(store)}
    assert by_id == {1: "story_opened", 2: "deferred"}


def test_control_room_bind_failure_is_nonfatal(env):
    cfg, paths, store, br = env
    a = ControlRoom(store, cfg, paths, br, port=0)
    assert a.start()
    try:
        b = ControlRoom(store, cfg, paths, br, port=a.port)
        assert b.start() is False
        assert any(e["kind"] == "control_room.bind_failed" for e in store.events(limit=10))
    finally:
        a.stop()


# ── đề xuất cải tiến (D-E) ───────────────────────────────────────────────────
def test_proposals_generated_with_evidence_deduped_and_capped(env):
    cfg, _, store, _ = env
    for i in range(4):
        seed_wave(store, f"W{i}", hours_ago=10 - i)
    ids = improve.sync(store, cfg)
    ps = {p["kind"]: p for p in sv.proposals(store)}
    assert {"yield", "cache"} <= set(ps) and len(ids) == len(ps)
    ev = ps["yield"]["evidence"]
    assert ev["mean_first_pass_yield"] == 0.56 and ev["waves"] == 4
    assert improve.sync(store, cfg) == []                                         # không lặp
    cfg2 = {**cfg, "improvement": {"max_per_week": 1}}
    store2_ids = improve.sync(store, cfg2)
    assert store2_ids == []


def test_cap_per_week_limits_new_proposals(env):
    cfg, _, store, _ = env
    for i in range(4):
        seed_wave(store, f"W{i}", hours_ago=10 - i)
    ids = improve.sync(store, {**cfg, "improvement": {"max_per_week": 1}})
    assert len(ids) == 1                                                          # chỉ giữ cái tác động cao nhất


def test_rejected_proposal_does_not_resurface_for_30_days(env):
    cfg, _, store, _ = env
    for i in range(4):
        seed_wave(store, f"W{i}", hours_ago=10 - i)
    improve.sync(store, cfg)
    pid = next(p["id"] for p in sv.proposals(store) if p["kind"] == "yield")
    assert improve.decide(store, pid, "reject")["status"] == "rejected"
    assert all(p["kind"] != "yield" or p["id"] == pid for p in sv.proposals(store))
    assert improve.sync(store, cfg) == []
    later = now_vn() + timedelta(days=31)
    assert any(p for p in improve.sync(store, cfg, now=later))                    # hết thời hiệu thì được nêu lại


def test_tool_violation_proposal_has_top_impact(env):
    cfg, _, store, _ = env
    seed_wave(store, "W1")
    Tracer(store.path, "W1").begin("lô x", "agent", "article-processor", span_id="W1.bad")
    Tracer(store.path, "W1").finish("W1.bad", "fail", tool_invoked=True)
    improve.sync(store, cfg)
    assert sv.proposals(store)[0]["kind"] == "invariant"


def test_open_story_failure_keeps_proposal_open(env):
    _, _, store, _ = env
    with store.conn() as c:
        c.execute("INSERT INTO ops_proposals(created_at, dedup_key, kind, title, impact) "
                  "VALUES (?,?,?,?,?)", (iso(), "k", "yield", "Đề xuất", 1))
    bad = lambda *a: SimpleNamespace(returncode=1, stdout="", stderr="harness lỗi")  # noqa: E731
    res = improve.decide(store, 1, "open_story", harness=bad)
    assert res["ok"] is False and sv.proposals(store)[0]["status"] == "open"
    assert improve.decide(store, 99, "defer")["ok"] is False
    assert improve.decide(store, 1, "xoa")["ok"] is False


# ── mandate tự gia hạn (D-A) ─────────────────────────────────────────────────
def _grant(paths, days_left):
    o = StandingOrder(level="L1", valid_until=(date.today() + timedelta(days=days_left)).isoformat(),
                      exists=True, created_by="human:level")
    save_order(paths.standing_order, o)


def test_mandate_renews_when_healthy_and_near_expiry(env):
    cfg, paths, store, _ = env
    store.set_state("clean_streak", "5")
    _grant(paths, 3)
    res = mandate.maybe_renew(store, cfg, paths)
    assert res["action"] == "renewed"
    o = load_order(paths.standing_order)
    assert o.created_by == "daemon:auto-renew" and o.level == "L1"
    assert date.fromisoformat(o.valid_until) == date.today() + timedelta(days=30)
    assert any(e["kind"] == "mandate.renewed" for e in store.events(limit=20))


def test_mandate_does_not_renew_when_far_from_expiry(env):
    cfg, paths, store, _ = env
    store.set_state("clean_streak", "9")
    _grant(paths, 20)
    assert mandate.maybe_renew(store, cfg, paths) is None


@pytest.mark.parametrize("setup,reason", [
    (lambda s: s.set_state("clean_streak", "2"), "chuỗi đợt sạch"),
    (lambda s: (s.set_state("clean_streak", "9"), s.set_state("fail_streak", "1")), "chuỗi đợt hỏng"),
    (lambda s: (s.set_state("clean_streak", "9"), s.emit("x", "đỏ", level="critical")), "mức đỏ"),
])
def test_mandate_blocked_by_unhealthy_system_and_alerts(env, setup, reason):
    cfg, paths, store, _ = env
    setup(store)
    _grant(paths, 3)
    res = mandate.maybe_renew(store, cfg, paths)
    assert res["action"] == "blocked" and any(reason in r for r in res["reasons"])
    assert date.fromisoformat(load_order(paths.standing_order).valid_until) \
        == date.today() + timedelta(days=3)                                       # hạn không đổi
    assert any("không tự gia hạn" in a["text"] for a in store.unsent_alerts())


def test_mandate_blocked_by_tool_violation_in_7_days(env):
    cfg, paths, store, _ = env
    store.set_state("clean_streak", "9")
    tr = Tracer(store.path, "W1")
    tr.begin("lô", "agent", "article-processor", span_id="W1.x")
    tr.finish("W1.x", "ok", denied_actions=True)
    ok, reasons = mandate.health(store, cfg)
    assert not ok and any("Zero-Tool" in r for r in reasons)


def test_expired_or_missing_mandate_is_never_auto_granted(env):
    cfg, paths, store, _ = env
    store.set_state("clean_streak", "9")
    assert mandate.maybe_renew(store, cfg, paths) is None                          # chưa từng cấp
    _grant(paths, -1)
    assert mandate.maybe_renew(store, cfg, paths) is None                          # đã hết hạn: người cấp lại
    assert load_order(paths.standing_order).effective_level() == "L0"


# ── Telegram: bản tin và lệnh giám sát (P3) ──────────────────────────────────
class Ctl:
    def __init__(self, cfg, paths, store, br):
        self.cfg, self.paths, self.store, self.breakers = cfg, paths, store, br


def test_digest_lists_agents_anomalies_and_open_proposals(env):
    cfg, paths, store, br = env
    seed_wave(store, "W1")
    with store.conn() as c:
        c.execute("INSERT INTO ops_proposals(created_at, dedup_key, kind, title, impact) "
                  "VALUES (?,?,?,?,?)", (iso(), "k", "yield", "x", 1))
    text = reports.digest_text(store, paths, br)
    assert "Bản tin giám sát" in text and "Mandate:" in text
    assert "- article-processor: 6 span" in text and "204.062" in text.replace(",", ".")
    assert "Khác thường:" in text and "Đề xuất cải tiến đang mở: 1" in text


def test_telegram_supervision_commands(env):
    cfg, paths, store, br = env
    seed_wave(store, "W1")
    ctl = Ctl(cfg, paths, store, br)
    m = commands.execute("/map", ctl).text
    assert "Bản đồ tác nhân" in m and "article-processor" in m and "master-orchestrator" in m
    t = commands.execute("/trace W1", ctl).text
    assert "Cây vết W1" in t and "analyze" in t and "nhận 56/100" in t and "repair1" in t
    assert "Cây vết W1" in commands.execute("/trace", ctl).text                    # mặc định đợt gần nhất
    a = commands.execute("/agent article-processor", ctl).text
    assert "Công cụ cho phép: không có" in a and "6 span" in a
    assert "Không có tác nhân" in commands.execute("/agent khong-co", ctl).text
    assert "Chưa có mandate" in commands.execute("/mandate", ctl).text
    assert "Hộp thư cải tiến trống" in commands.execute("/improve", ctl).text


def test_telegram_improve_buttons_and_decision_are_audited(env):
    cfg, paths, store, br = env
    with store.conn() as c:
        c.execute("INSERT INTO ops_proposals(created_at, dedup_key, kind, title, impact) "
                  "VALUES (?,?,?,?,?)", (iso(), "k", "yield", "Đề xuất A", 5))
    ctl = Ctl(cfg, paths, store, br)
    r = commands.execute("/improve", ctl)
    assert [b[1] for b in r.buttons[0]] == ["/prop open_story 1", "/prop defer 1", "/prop reject 1"]
    assert all(len(b[1]) <= 64 for row in r.buttons for b in row)                  # giới hạn callback_data
    assert "Đã defer" in commands.execute("/prop defer 1", ctl).text
    kinds = [e["kind"] for e in store.events(limit=30)]
    assert "proposal.decided" in kinds and "human.command" in kinds
    assert "Dùng:" in commands.execute("/prop", ctl).text


def test_wave_done_pushes_no_alert_unless_configured(env, tmp_path):
    from src.ops.wave_flow import WaveSpec, WaveSteps

    cfg, paths, store, _ = env
    spec = WaveSpec("W1", "2026-10-01", "T1", "L1")
    store.upsert_wave("W1", status="SENSED")
    steps = WaveSteps(store, cfg, paths, db_probe=lambda: (True, ""))
    steps.finalize(spec, "DONE", "100/100 bài phân tích, đã nạp DB.")
    assert not [a for a in store.unsent_alerts() if "xong" in a["text"]]
    cfg2 = {**cfg, "alerts": {**cfg["alerts"], "push_wave_info": True}}
    steps2 = WaveSteps(store, cfg2, paths, db_probe=lambda: (True, ""))
    store.upsert_wave("W2", status="SENSED")
    steps2.finalize(WaveSpec("W2", "2026-10-01", "T1", "L1"), "DONE", "ok")
    assert [a for a in store.unsent_alerts() if "W2" in a["text"]]


def test_attention_orders_by_severity_and_drives_health(env):
    cfg, paths, store, breakers = env
    st = {"daemon": {"alive": False, "heartbeat_age_s": None}, "kill_switch": False, "paused": True,
          "breakers": [{"provider": "agy", "state": "OPEN", "reason": "AUTH"}],
          "mandate": {"exists": False, "days_left": None}, "alerts_unsent": 2, "proposals_open": 1}
    items = sv.attention(store, st)
    assert [i["severity"] for i in items] == sorted((i["severity"] for i in items),
                                                    key={"bad": 0, "warn": 1, "info": 2}.get)
    assert items[0]["severity"] == "bad"
    assert any(i["action"] == "/reset agy" for i in items)
    assert sv.health_of(items)["level"] == "bad"


def test_health_levels_ignore_info_only():
    assert sv.health_of([])["level"] == "ok"
    assert sv.health_of([{"severity": "info"}])["level"] == "ok"
    assert sv.health_of([{"severity": "info"}, {"severity": "warn"}])["level"] == "warn"
