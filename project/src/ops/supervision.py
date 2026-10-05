"""Mô hình đọc cho giám sát: bản đồ agent, danh sách đợt, cây vết, thẻ tác nhân, sự cố."""

from __future__ import annotations

import json
import sqlite3
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.ops.breakers import Breakers
from src.ops.config import OpsPaths
from src.ops.order import load_order
from src.ops import pipeline_spec
from src.ops.present import (BREAKER_STATE, FAILURE_CLASS, WAVE_STATUS, label, success_rate)
from src.ops.store import OpsStore, now_vn, parse_iso

AGENTS_DIR = Path(__file__).resolve().parents[3] / ".agents"

# Dây chuyền chính của một đợt, theo thứ tự dữ liệu chảy (lọc theo trạng thái trong registry).
MAIN_CHAIN = pipeline_spec.main_chain()
TOP_LEFT = ("pipeline-radar",)
TOP_RIGHT = ("ops-sentinel", "improvement-proposer")
OUTSIDE_WAVE = ("scraper-orchestrator",)
MAP_WIDTH = 1180

_cache: dict[str, tuple[float, Any]] = {}


def _load_yaml(name: str) -> dict:
    """Đọc một tệp YAML của `.agents/`, nạp lại khi tệp đổi."""
    import yaml

    path = AGENTS_DIR / name
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    hit = _cache.get(name)
    if hit and hit[0] == mtime:
        return hit[1]
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _cache[name] = (mtime, data)
    return data


def registry() -> dict[str, dict]:
    """Trả về các tác nhân trong `registry.yaml` theo id."""
    return {a["id"]: a for a in _load_yaml("registry.yaml").get("agents", [])
            if isinstance(a, dict) and "id" in a}


def _rows(store: OpsStore, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with store.conn() as c:
        return c.execute(sql, params).fetchall()


def _attrs(row: sqlite3.Row | dict) -> dict:
    try:
        return json.loads(row["attrs_json"] or "{}")
    except (ValueError, TypeError):
        return {}


def _today() -> str:
    return now_vn().date().isoformat()


def _tokens(attrs: dict) -> int:
    return int((attrs.get("usage") or {}).get("total_tokens") or 0)


# ── trạng thái chung ─────────────────────────────────────────────────────────
def mandate_info(paths: OpsPaths) -> dict:
    """Mô tả mandate (standing order) hiện hành.

    Args:
        paths: Đường dẫn vận hành.

    Returns:
        Từ điển: mức, ngày hết hạn, số ngày còn lại.
    """
    order = load_order(paths.standing_order)
    left = None
    if order.exists:
        try:
            left = (datetime.fromisoformat(order.valid_until).date() - now_vn().date()).days
        except ValueError:
            left = None
    return {"level": order.effective_level(), "declared": order.level, "exists": order.exists,
            "valid_until": order.valid_until, "days_left": left, "provider": order.provider,
            "failover": order.failover, "created_by": order.created_by}


def state(store: OpsStore, cfg: dict, paths: OpsPaths, breakers: Breakers) -> dict:
    """Gom trạng thái cho dải trạng thái của màn Toàn cảnh.

    Args:
        store: Store vận hành.
        cfg: Cấu hình đầy đủ.
        paths: Đường dẫn vận hành.
        breakers: Breaker theo provider.

    Returns:
        Từ điển trạng thái.
    """
    hb = parse_iso(store.get_state("heartbeat_at"))
    age = (now_vn() - hb).total_seconds() if hb else None
    sensor = json.loads(store.get_state("sensor:last") or "{}")
    w = store.active_wave()
    with store.conn() as c:
        unsent = c.execute("SELECT COUNT(*) FROM ops_alerts WHERE sent_at IS NULL").fetchone()[0]
        open_prop = c.execute("SELECT COUNT(*) FROM ops_proposals WHERE status = 'open'").fetchone()[0]
    snapshot = {
        "now": now_vn().isoformat(timespec="seconds"),
        "daemon": {"alive": age is not None and age < 180, "heartbeat_age_s": age},
        "paused": store.get_state("paused") == "1", "kill_switch": paths.kill_switch.exists(),
        "capture": store.get_state("capture_mode", "?"),
        "mandate": mandate_info(paths),
        "breakers": [{"provider": b.provider, "state": b.state, "reason": b.reason,
                      "failures": b.consecutive_failures, "reopen_at": b.reopen_at}
                     for b in breakers.all()],
        "pending": {"total": sensor.get("total"), "per_date": sensor.get("per_date"),
                    "oldest_age_min": sensor.get("oldest_age_min"),
                    "backlog_all": sensor.get("backlog_all"), "at": sensor.get("at"),
                    "reason": sensor.get("reason")},
        "active_wave": ({"wave_id": w["wave_id"], "status": w["status"], "step": w["step"],
                         "n_articles": w["n_articles"], "opened_at": w["opened_at"]} if w else None),
        "streaks": {"clean": int(store.get_state("clean_streak", "0") or 0),
                    "fail": int(store.get_state("fail_streak", "0") or 0)},
        "alerts_unsent": unsent, "proposals_open": open_prop,
    }
    items = attention(store, snapshot)
    snapshot["attention"] = items
    snapshot["health"] = health_of(items)
    return snapshot


_SEVERITY_RANK = {"bad": 0, "warn": 1, "info": 2}


def attention(store: OpsStore, st: dict) -> list[dict]:
    """Liệt kê việc cần người xem, nặng trước.

    Args:
        store: Store vận hành.
        st: Trạng thái đã gom (các khoá daemon, paused, kill_switch, breakers, mandate,
            alerts_unsent, proposals_open).

    Returns:
        Danh sách {severity, title, action}; severity là bad, warn hoặc info.
    """
    items: list[dict] = []

    def add(severity: str, title: str, action: str) -> None:
        items.append({"severity": severity, "title": title, "action": action})

    d = st["daemon"]
    if not d["alive"]:
        why = ("chưa chạy" if d["heartbeat_age_s"] is None
               else f"im lặng {round(d['heartbeat_age_s'] / 60)} phút")
        add("bad", f"Daemon {why}", "Start-ScheduledTask news-scape-ops")
    if st["kill_switch"]:
        add("bad", "Cờ AGY_STOP đang bật, không đợt nào được mở", "/unstop")
    if st["paused"]:
        add("warn", "Đang tạm dừng mở đợt mới", "/resume")
    for b in st["breakers"]:
        if b["state"] != "CLOSED":
            sev = "bad" if b["reason"] == "AUTH" else "warn"
            act = f"/reset {b['provider']}" if b["reason"] == "AUTH" else "chờ breaker tự thử lại"
            add(sev, f"Breaker {b['provider']} {label(BREAKER_STATE, b['state']).lower()} "
                     f"({label(FAILURE_CLASS, b['reason']).lower()})", act)
    with store.conn() as c:
        held = c.execute("SELECT wave_id, status, reason FROM ops_waves WHERE status IN "
                         "('PARKED','FAILED') ORDER BY opened_at DESC LIMIT 5").fetchall()
    for w in held:
        add("bad" if w["status"] == "FAILED" else "warn",
            f"Đợt {w['wave_id']} {label(WAVE_STATUS, w['status']).lower()}: "
            f"{(w['reason'] or '')[:100]}", f"/retry {w['wave_id']} hoặc /cancel {w['wave_id']}")
    m = st["mandate"]
    if not m["exists"]:
        add("info", "Chưa có mandate: daemon ở L0, không tự mở đợt", "/level L1")
    elif m["days_left"] is not None and m["days_left"] <= 3:
        add("warn", f"Mandate còn {m['days_left']} ngày", "/mandate")
    if st["alerts_unsent"]:
        add("warn", f"{st['alerts_unsent']} tin chưa gửi được tới Telegram",
            "kiểm token và mã chat Telegram")
    if st["proposals_open"]:
        add("info", f"{st['proposals_open']} đề xuất cải tiến đang chờ quyết định",
            "mở màn Cải tiến")
    return sorted(items, key=lambda i: _SEVERITY_RANK[i["severity"]])


def health_of(items: list[dict]) -> dict:
    """Tóm tắt sức khoẻ tổng thể từ danh sách việc cần người.

    Args:
        items: Kết quả của `attention`.

    Returns:
        Từ điển {level, label}; level là ok, warn hoặc bad. Mục `info` không đổi mức.
    """
    levels = {i["severity"] for i in items}
    if "bad" in levels:
        return {"level": "bad", "label": "Sự cố"}
    if "warn" in levels:
        return {"level": "warn", "label": "Cần xem"}
    return {"level": "ok", "label": "Khoẻ"}


# ── bản đồ agent ─────────────────────────────────────────────────────────────
def _actor_runtime(store: OpsStore) -> dict[str, dict]:
    """Thống kê span theo tác nhân: đang chạy, lần cuối, số liệu trong ngày."""
    out: dict[str, dict] = {}
    today = _today()
    for r in _rows(store, "SELECT actor_id, status, started_at, ended_at, attrs_json, kind "
                          "FROM ops_spans WHERE actor_id IS NOT NULL AND started_at >= ? "
                          "ORDER BY started_at", (today,)):
        d = out.setdefault(r["actor_id"], {"spans": 0, "ok": 0, "fail": 0, "partial": 0,
                                           "tokens": 0, "running": 0, "last_status": None,
                                           "last_at": None, "tool_violations": 0})
        d["spans"] += 1
        d["last_status"], d["last_at"] = r["status"], r["ended_at"] or r["started_at"]
        if r["status"] == "running":
            d["running"] += 1
        elif r["status"] == "ok":
            d["ok"] += 1
        elif r["status"] == "partial":
            d["partial"] += 1
        elif r["status"] in ("fail", "timeout", "interrupted"):
            d["fail"] += 1
        a = _attrs(r)
        d["tokens"] += _tokens(a)
        d["tool_violations"] += int(bool(a.get("tool_invoked") or a.get("denied_actions")))
    return out


def _node_state(spec: dict, rt: dict | None, alive: bool, active_wave: bool) -> str:
    if spec.get("status") == "draft":
        return "draft"
    if rt and rt["running"]:
        return "run"
    if spec["id"] == "master-orchestrator":
        return "run" if active_wave else ("ok" if alive else "fail")
    if rt and rt["last_status"] in ("fail", "timeout"):
        return "fail"
    if rt and rt["spans"]:
        return "ok"
    return "idle"


def build_map(store: OpsStore, cfg: dict, paths: OpsPaths, breakers: Breakers) -> dict:
    """Dựng bản đồ agent sống: nút theo registry, trạng thái theo vết.

    Args:
        store: Store vận hành.
        cfg: Cấu hình đầy đủ.
        paths: Đường dẫn vận hành.
        breakers: Breaker theo provider.

    Returns:
        Từ điển gồm nút (kèm toạ độ), cạnh, kho dữ liệu và dải trạng thái.
    """
    reg = registry()
    rt = _actor_runtime(store)
    st = state(store, cfg, paths, breakers)
    alive, active = st["daemon"]["alive"], st["active_wave"] is not None

    width = MAP_WIDTH

    def node(aid: str, x: int, y: int, w: int, h: int) -> dict:
        spec = reg[aid]
        r = rt.get(aid)
        return {"id": aid, "class": spec.get("class"), "status": spec.get("status"),
                "skill": Path(str(spec.get("skill") or "")).parent.name or None,
                "model": spec.get("model"), "tools": len(spec.get("tools_allowed") or []),
                "x": x, "y": y, "w": w, "h": h,
                "state": _node_state(spec, r, alive, active),
                "stats": ({**r, "success_rate": success_rate(r["ok"], r["fail"], r["partial"])}
                          if r else {"spans": 0, "ok": 0, "fail": 0, "partial": 0, "tokens": 0,
                                     "running": 0, "success_rate": None, "last_status": None,
                                     "last_at": None, "tool_violations": 0})}

    nodes: list[dict] = []
    if "master-orchestrator" in reg:
        nodes.append(node("master-orchestrator", (width - 400) // 2, 62, 400, 52))
    for i, aid in enumerate(a for a in TOP_LEFT if a in reg and reg[a].get("status") != "retired"):
        nodes.append(node(aid, 30 + i * 210, 62, 200, 52))
    right = [a for a in TOP_RIGHT if a in reg and reg[a].get("status") != "retired"]
    for i, aid in enumerate(right):
        nodes.append(node(aid, width - 16 - (len(right) - i) * 180 + 10, 62, 170, 52))
    chain = [a for a in MAIN_CHAIN if a in reg and reg[a].get("status") == "active"]
    widths = {a: max(104, int(len(a) * 6.9) + 16) for a in chain}
    gap = max(8, int((width - 32 - sum(widths.values())) / max(1, len(chain) - 1)))
    x = 16
    for aid in chain:
        nodes.append(node(aid, x, 190, widths[aid], 64))
        x += widths[aid] + gap
    drafts = [a for a, s in reg.items() if s.get("status") == "draft"
              and a not in TOP_LEFT + TOP_RIGHT and a != "master-orchestrator"]
    for i, aid in enumerate(drafts):
        nodes.append(node(aid, 16 + i * 205, 300, 195, 44))
    edges = [{"from": a, "to": b, "dashed": a in OUTSIDE_WAVE or b in OUTSIDE_WAVE}
             for a, b in zip(chain, chain[1:])]
    stores = [{"id": "monocle", "name": "monocle.db", "sub": "bài · l1_outputs · agent_outputs"},
              {"id": "ops", "name": "ops.db", "sub": "ops_spans · ops_waves · ops_alerts"},
              {"id": "files", "name": "agent_tasks · agent_outputs_article", "sub": "packet và đầu ra thô"}]
    return {"width": width, "height": 420, "nodes": nodes, "edges": edges, "chain": chain,
            "stores": stores, "state": st}


# ── đợt và cây vết ───────────────────────────────────────────────────────────
def waves(store: OpsStore, limit: int = 20) -> list[dict]:
    """Liệt kê đợt gần nhất kèm số đo rút ra từ vết.

    Args:
        store: Store vận hành.
        limit: Số đợt tối đa.

    Returns:
        Danh sách đợt, mới trước.
    """
    out = []
    for w in store.waves(limit):
        ag = _rows(store, "SELECT s.attrs_json, p.name AS step FROM ops_spans s "
                          "LEFT JOIN ops_spans p ON p.span_id = s.parent_id "
                          "WHERE s.trace_id = ? AND s.kind = 'agent'", (w["wave_id"],))
        tokens = sum(_tokens(_attrs(a)) for a in ag)
        repair = sum(_tokens(_attrs(a)) for a in ag if str(a["step"] or "").startswith("repair"))
        steps = _rows(store, "SELECT name, attrs_json FROM ops_spans WHERE trace_id = ? "
                             "AND kind = 'step' AND name = 'analyze'", (w["wave_id"],))
        first = None
        if steps:
            a = _attrs(steps[0])
            if a.get("total"):
                first = round(int(a.get("received") or 0) / int(a["total"]), 3)
        o, f = parse_iso(w["opened_at"]), parse_iso(w["finished_at"])
        out.append({"wave_id": w["wave_id"], "status": w["status"], "step": w["step"],
                    "target_date": w["target_date"], "n_articles": w["n_articles"],
                    "trigger": w["trigger"], "level": w["level"], "provider": w["provider"],
                    "opened_at": w["opened_at"], "reason": w["reason"],
                    "duration_s": round((f - o).total_seconds()) if o and f else None,
                    "tokens": tokens, "repair_tokens": repair,
                    "repair_share": round(repair / tokens, 3) if tokens else None,
                    "first_pass_yield": first})
    return out


def trace_of(store: OpsStore, wave_id: str) -> dict:
    """Trả về mọi span của một đợt kèm độ lệch thời gian cho biểu đồ Gantt.

    Args:
        store: Store vận hành.
        wave_id: Mã đợt.

    Returns:
        Từ điển gồm `spans` (đã sắp theo thời gian) và `duration_ms`.
    """
    rows = _rows(store, "SELECT * FROM ops_spans WHERE trace_id = ? ORDER BY started_at, span_id",
                 (wave_id,))
    now = now_vn()
    starts = [parse_iso(r["started_at"]) for r in rows if parse_iso(r["started_at"])]
    if not starts:
        return {"wave_id": wave_id, "spans": [], "duration_ms": 0}
    t0 = min(starts)
    spans, end_max = [], 0
    for r in rows:
        s = parse_iso(r["started_at"])
        e = parse_iso(r["ended_at"]) or now
        off, dur = (s - t0).total_seconds() * 1000, max(0.0, (e - s).total_seconds() * 1000)
        end_max = max(end_max, off + dur)
        a = _attrs(r)
        spans.append({"span_id": r["span_id"], "parent_id": r["parent_id"], "kind": r["kind"],
                      "name": r["name"], "actor_id": r["actor_id"], "skill": r["skill"],
                      "entrypoint": r["entrypoint"], "status": r["status"], "attrs": a,
                      "tokens": _tokens(a), "input_ref": r["input_ref"], "output_ref": r["output_ref"],
                      "offset_ms": round(off), "duration_ms": round(dur)})
    return {"wave_id": wave_id, "spans": spans, "duration_ms": round(end_max)}


# ── tác nhân ─────────────────────────────────────────────────────────────────
def agent_card(store: OpsStore, agent_id: str, days: int = 7) -> dict | None:
    """Dựng thẻ một tác nhân: đặc tả từ registry và KPI các ngày gần đây.

    Args:
        store: Store vận hành.
        agent_id: Mã tác nhân trong registry.
        days: Số ngày xu hướng.

    Returns:
        Từ điển thẻ, hoặc None khi registry không có tác nhân này.
    """
    spec = registry().get(agent_id)
    if not spec:
        return None
    since = (now_vn() - timedelta(days=days)).date().isoformat()
    rows = _rows(store, "SELECT status, started_at, ended_at, attrs_json, name, trace_id, span_id "
                        "FROM ops_spans WHERE actor_id = ? AND started_at >= ? ORDER BY started_at",
                 (agent_id, since))
    per_day: dict[str, dict] = {}
    violations = []
    for r in rows:
        day = r["started_at"][:10]
        d = per_day.setdefault(day, {"day": day, "spans": 0, "ok": 0, "fail": 0, "partial": 0,
                                     "tokens": 0, "latency": []})
        d["spans"] += 1
        d["ok"] += int(r["status"] == "ok")
        d["partial"] += int(r["status"] == "partial")
        d["fail"] += int(r["status"] in ("fail", "timeout", "interrupted"))
        a = _attrs(r)
        d["tokens"] += _tokens(a)
        if a.get("latency_s"):
            d["latency"].append(float(a["latency_s"]))
        if a.get("tool_invoked") or a.get("denied_actions"):
            violations.append({"span_id": r["span_id"], "trace_id": r["trace_id"]})
    trend = []
    for d in per_day.values():
        lat = d.pop("latency")
        d["success_rate"] = success_rate(d["ok"], d["fail"], d["partial"])
        d["avg_latency_s"] = round(sum(lat) / len(lat), 1) if lat else None
        trend.append(d)
    recent = [{"span_id": r["span_id"], "trace_id": r["trace_id"], "name": r["name"],
               "status": r["status"], "started_at": r["started_at"], "tokens": _tokens(_attrs(r))}
              for r in rows[-15:]][::-1]
    keep = ("id", "class", "status", "model", "skill", "entrypoint", "cli", "responsibility",
            "tools_allowed", "io_boundary", "dod_contract", "kpis", "cost_budget", "invariants",
            "activation_gate", "intent")
    return {"spec": {k: spec[k] for k in keep if k in spec}, "trend": trend, "recent": recent,
            "violations": violations}


def kpi_series(store: OpsStore, days: int = 14) -> dict:
    """Chuỗi KPI theo đợt từ bảng `ops_waves` và vết, dùng cho bản tin và phát hiện bất thường.

    Args:
        store: Store vận hành.
        days: Cửa sổ ngày.

    Returns:
        Từ điển các danh sách theo thứ tự thời gian: first_pass_yield, tokens_per_article,
        repair_share, avg_latency_s.
    """
    since = (now_vn() - timedelta(days=days)).date().isoformat()
    out = {"first_pass_yield": [], "tokens_per_article": [], "repair_share": [], "avg_latency_s": []}
    for w in reversed(waves(store, 200)):
        if w["status"] != "DONE" or w["opened_at"][:10] < since or not w["n_articles"]:
            continue
        if w["first_pass_yield"] is not None:
            out["first_pass_yield"].append(w["first_pass_yield"])
        if w["tokens"]:
            out["tokens_per_article"].append(w["tokens"] / w["n_articles"])
        if w["repair_share"] is not None:
            out["repair_share"].append(w["repair_share"])
        lat = [_attrs(r).get("latency_s") for r in _rows(
            store, "SELECT attrs_json FROM ops_spans WHERE trace_id = ? AND kind = 'agent'",
            (w["wave_id"],))]
        lat = [float(x) for x in lat if x]
        if lat:
            out["avg_latency_s"].append(sum(lat) / len(lat))
    return out


def anomalies(store: OpsStore, min_waves: int = 5, sigma: float = 2.0) -> list[dict]:
    """Tìm số đo của đợt gần nhất lệch quá `sigma` độ lệch chuẩn so với các đợt trước.

    Args:
        store: Store vận hành.
        min_waves: Số đợt tối thiểu để so sánh (D-D).
        sigma: Ngưỡng lệch.

    Returns:
        Danh sách {metric, value, mean, stdev}.
    """
    out = []
    for metric, series in kpi_series(store, 7).items():
        if len(series) < min_waves + 1:
            continue
        base, last = series[:-1], series[-1]
        sd = statistics.pstdev(base)
        mean = statistics.fmean(base)
        if sd > 0 and abs(last - mean) > sigma * sd:
            out.append({"metric": metric, "value": round(last, 3), "mean": round(mean, 3),
                        "stdev": round(sd, 3)})
    return out


# ── sự cố ────────────────────────────────────────────────────────────────────
def incidents(store: OpsStore, breakers: Breakers) -> dict:
    """Tập hợp breaker, probe, sự kiện bất thường và chẩn đoán gần đây.

    Args:
        store: Store vận hành.
        breakers: Breaker theo provider.

    Returns:
        Từ điển các phần của màn Sự cố.
    """
    probes = {}
    with store.conn() as c:
        for r in c.execute("SELECT key, value, updated_at FROM ops_state WHERE key LIKE 'probe:%'"):
            probes[r["key"][6:]] = {"state": r["value"], "since": r["updated_at"]}
    events = [{"ts": e["ts"], "level": e["level"], "kind": e["kind"], "message": e["message"],
               "wave_id": e["wave_id"]} for e in store.events(limit=40, min_level="warn")]
    diag = [{"ts": e["ts"], "message": e["message"], "data": json.loads(e["data_json"] or "{}")}
            for e in _rows(store, "SELECT * FROM ops_events WHERE kind = 'sentinel.diagnosis' "
                                  "ORDER BY id DESC LIMIT 5")]
    return {"breakers": [{"provider": b.provider, "state": b.state, "reason": b.reason,
                          "failures": b.consecutive_failures, "reopen_at": b.reopen_at}
                         for b in breakers.all()],
            "probes": probes, "events": events[::-1], "diagnoses": diag}


# ── cải tiến ─────────────────────────────────────────────────────────────────
def proposals(store: OpsStore, status: str | None = None, limit: int = 50) -> list[dict]:
    """Liệt kê đề xuất cải tiến, mở trước và tác động cao trước.

    Args:
        store: Store vận hành.
        status: Lọc theo trạng thái.
        limit: Số tối đa.

    Returns:
        Danh sách đề xuất.
    """
    sql = "SELECT * FROM ops_proposals"
    params: tuple = ()
    if status:
        sql += " WHERE status = ?"
        params = (status,)
    sql += " ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, impact DESC, id DESC LIMIT ?"
    return [{"id": r["id"], "created_at": r["created_at"], "kind": r["kind"], "title": r["title"],
             "evidence": json.loads(r["evidence_json"] or "{}"), "impact": r["impact"],
             "status": r["status"], "decided_at": r["decided_at"], "story_id": r["story_id"]}
            for r in _rows(store, sql, params + (limit,))]
