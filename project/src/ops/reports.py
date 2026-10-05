"""Dựng văn bản trạng thái, danh sách đợt, nhật ký, bản tin và tra cứu tác nhân cho người vận hành."""

from __future__ import annotations

import json

from src.ops import supervision as sv
from src.ops.breakers import Breakers
from src.ops.config import OpsPaths
from src.ops.order import load_order
from src.ops.present import (BREAKER_STATE, CAPTURE_MODE, FAILURE_CLASS, NODE_STATE,
                             SPAN_STATUS, TRIGGER, WAVE_STATUS, clip_lines, fmt_date, fmt_datetime,
                             fmt_duration, fmt_int, fmt_pct, fmt_time, label, success_rate)
from src.ops.store import OpsStore, now_vn, parse_iso


def heartbeat_age_s(store: OpsStore) -> float | None:
    """Tính số giây từ nhịp tim gần nhất của daemon.

    Args:
        store: Store vận hành.

    Returns:
        Số giây, hoặc None khi chưa có nhịp tim.
    """
    ts = parse_iso(store.get_state("heartbeat_at"))
    return (now_vn() - ts).total_seconds() if ts else None


def status_text(store: OpsStore, paths: OpsPaths, breakers: Breakers) -> str:
    """Dựng bản trạng thái rút gọn.

    Args:
        store: Store vận hành.
        paths: Đường dẫn vận hành.
        breakers: Breaker theo provider.

    Returns:
        Văn bản nhiều dòng.
    """
    age = heartbeat_age_s(store)
    if age is None:
        alive = "chưa chạy"
    elif age < 180:
        alive = "sống"
    else:
        alive = f"im lặng {fmt_duration(age)}"
    order = load_order(paths.standing_order)
    mandate = (f"mandate {order.effective_level()} (hạn {fmt_date(order.valid_until)})"
               if order.exists else "chưa có mandate (L0)")
    lines = [f"Daemon: {alive} · {mandate}",
             f"Tạm dừng: {'có' if store.get_state('paused') == '1' else 'không'} · "
             f"AGY_STOP: {'bật' if paths.kill_switch.exists() else 'tắt'} · "
             f"provider {order.provider} · failover {order.failover}"]
    sensor = store.get_state("sensor:last")
    if sensor:
        s = json.loads(sensor)
        per = ", ".join(f"{fmt_date(d)}: {fmt_int(n)}" for d, n in s.get("per_date", []))
        age_txt = (f" · lâu nhất {fmt_duration(s['oldest_age_min'] * 60)}"
                   if s.get("oldest_age_min") else "")
        lines.append(f"Bài chờ: {fmt_int(s.get('total', 0))} ({per}){age_txt}")
        if s.get("backlog_all") is not None:
            lines.append(f"Tồn đọng: {fmt_int(s['backlog_all'])} bài (ngoài phạm vi tự động)")
        took = (f" · đo {fmt_duration(s['took_s'])} lúc {fmt_time(s['at'])}"
                if s.get("took_s") is not None else "")
        lines.append(f"Sensor: {s.get('reason', '')}{took}")
    lines.append(f"Cào tin: {label(CAPTURE_MODE, store.get_state('capture_mode'))}")
    for b in breakers.all():
        if b.state != "CLOSED" or b.consecutive_failures:
            lines.append(f"Breaker {b.provider}: {label(BREAKER_STATE, b.state)} "
                         f"({label(FAILURE_CLASS, b.last_class)}, {b.consecutive_failures} lỗi) · "
                         f"mở lại {fmt_datetime(b.reopen_at) if b.reopen_at else 'khi reset'}")
    w = store.active_wave()
    if w:
        lines.append(f"Đợt đang chạy: {w['wave_id']} · {label(WAVE_STATUS, w['status'])} "
                     f"({w['step']}) · {fmt_int(w['n_articles']) if w['n_articles'] else '?'} bài "
                     f"· mở lúc {fmt_time(w['opened_at'])}")
    with store.conn() as c:
        unsent = c.execute("SELECT COUNT(*) FROM ops_alerts WHERE sent_at IS NULL").fetchone()[0]
    if unsent:
        lines.append(f"Tin chưa gửi: {unsent}")
    return "\n".join(lines)


def waves_text(store: OpsStore, limit: int = 8) -> str:
    """Liệt kê các đợt gần nhất.

    Args:
        store: Store vận hành.
        limit: Số đợt.

    Returns:
        Văn bản nhiều dòng.
    """
    rows = store.waves(limit)
    if not rows:
        return "Chưa có đợt nào do daemon chạy."
    out = []
    for w in rows:
        out.append(f"{w['wave_id']} · {label(WAVE_STATUS, w['status'])} · {fmt_date(w['target_date'])} · "
                   f"{fmt_int(w['n_articles']) if w['n_articles'] else '?'} bài · "
                   f"{label(TRIGGER, w['trigger'])} · {w['level']}" + (f"\n   {w['reason'][:160]}" if w["reason"] else ""))
    return "\n".join(out)


def log_text(store: OpsStore, limit: int = 15, wave_id: str | None = None) -> str:
    """Liệt kê sự kiện gần nhất.

    Args:
        store: Store vận hành.
        limit: Số sự kiện.
        wave_id: Lọc theo đợt.

    Returns:
        Văn bản nhiều dòng.
    """
    rows = store.events(limit=limit, wave_id=wave_id)
    if not rows:
        return "Chưa có sự kiện."
    return clip_lines("\n".join(f"{fmt_time(r['ts'])} {r['level'][:4]:4} {r['kind']}: "
                                f"{r['message'][:200]}" for r in rows))


def _agent_lines(store: OpsStore, limit: int = 12) -> list[str]:
    """Mỗi tác nhân có span trong ngày một dòng: số span, tỷ lệ thành công, token, độ trễ."""
    lat: dict[str, list[float]] = {}
    for r in sv._rows(store, "SELECT actor_id, attrs_json FROM ops_spans WHERE kind = 'agent' "
                             "AND started_at >= ?", (sv._today(),)):
        v = sv._attrs(r).get("latency_s")
        if v:
            lat.setdefault(r["actor_id"], []).append(float(v))
    lines = []
    for aid, d in sorted(sv._actor_runtime(store).items(), key=lambda kv: -kv[1]["spans"]):
        rate = fmt_pct(success_rate(d["ok"], d["fail"], d["partial"]))
        extra = f" · {fmt_int(d['tokens'])} token" if d["tokens"] else ""
        if aid in lat:
            extra += f" · trung bình {fmt_duration(sum(lat[aid]) / len(lat[aid]))}"
        viol = f" · VI PHẠM công cụ {d['tool_violations']}" if d["tool_violations"] else ""
        lines.append(f"- {aid}: {d['spans']} span · thành công {rate}{extra}{viol}")
    return lines[:limit]


def digest_text(store: OpsStore, paths: OpsPaths, breakers: Breakers) -> str:
    """Dựng bản tin giám sát: mandate, đợt trong ngày, từng tác nhân, điểm khác thường.

    Args:
        store: Store vận hành.
        paths: Đường dẫn vận hành.
        breakers: Breaker theo provider.

    Returns:
        Văn bản bản tin.
    """
    today = now_vn().date().isoformat()
    with store.conn() as c:
        rows = c.execute("SELECT status, COUNT(*) n, SUM(COALESCE(n_articles,0)) a "
                         "FROM ops_waves WHERE substr(opened_at,1,10) = ? GROUP BY status",
                         (today,)).fetchall()
        problems = c.execute("SELECT COUNT(*) FROM ops_events WHERE substr(ts,1,10) = ? "
                             "AND level IN ('error','critical')", (today,)).fetchone()[0]
        parked = c.execute("SELECT wave_id, reason FROM ops_waves WHERE status IN "
                           "('PARKED','FAILED') AND substr(opened_at,1,10) = ?",
                           (today,)).fetchall()
        open_prop = c.execute("SELECT COUNT(*) FROM ops_proposals WHERE status = 'open'").fetchone()[0]
    by = {r["status"]: (r["n"], r["a"]) for r in rows}
    done_n, done_a = by.get("DONE", (0, 0))
    m = sv.mandate_info(paths)
    mand = (f"{m['level']} · còn {m['days_left']} ngày (hạn {fmt_date(m['valid_until'])})"
            if m["exists"] and m["days_left"] is not None else "chưa cấp (L0)")
    lines = [f"Bản tin giám sát {fmt_datetime(now_vn().isoformat())}",
             f"Mandate: {mand} · chuỗi đợt sạch {store.get_state('clean_streak', '0')}",
             f"Đợt hôm nay: {sum(v[0] for v in by.values())} (xong {done_n}, {fmt_int(done_a)} bài) · "
             f"lỗi hoặc tạm dừng {len(parked)} · sự kiện mức lỗi trở lên {problems}"]
    ag = _agent_lines(store)
    lines.append("Tác nhân hôm nay:" if ag else "Tác nhân hôm nay: chưa có span nào.")
    lines += ag
    an = sv.anomalies(store)
    lines.append("Khác thường: " + ("; ".join(f"{a['metric']} {a['value']} (trung bình {a['mean']})"
                                              for a in an) if an else "không có"))
    if open_prop:
        lines.append(f"Đề xuất cải tiến đang mở: {open_prop} (gõ /improve)")
    if parked:
        lines.append("Cần người xem:")
        lines += [f"  {p['wave_id']}: {(p['reason'] or '')[:120]} (gõ /retry {p['wave_id']} "
                  f"hoặc /cancel {p['wave_id']})" for p in parked[:5]]
    lines.append("")
    lines.append(status_text(store, paths, breakers))
    return clip_lines("\n".join(lines))


def map_text(store: OpsStore, cfg: dict, paths: OpsPaths, breakers: Breakers) -> str:
    """Sơ đồ chữ trạng thái từng tác nhân (lệnh `/map`).

    Args:
        store: Store vận hành.
        cfg: Cấu hình đầy đủ.
        paths: Đường dẫn vận hành.
        breakers: Breaker theo provider.

    Returns:
        Văn bản nhiều dòng.
    """
    m = sv.build_map(store, cfg, paths, breakers)
    by = {n["id"]: n for n in m["nodes"]}
    lines = ["Bản đồ tác nhân (vết hôm nay)"]
    for aid in ["master-orchestrator", *m["chain"]]:
        n = by.get(aid)
        if not n:
            continue
        st = n["stats"]
        tail = (f" · {st['spans']} span" + (f" · {fmt_int(st['tokens'])} token" if st["tokens"] else "")
                if st["spans"] else "")
        arrow = "  " if aid == "master-orchestrator" else "→ "
        lines.append(f"{arrow}{aid} [{n['class']}] {label(NODE_STATE, n['state'])}{tail}")
    side = [n for n in m["nodes"] if n["id"] not in m["chain"] and n["id"] != "master-orchestrator"]
    if side:
        lines.append("Khác: " + ", ".join(f"{n['id']} ({label(NODE_STATE, n['state']).lower()})"
                                           for n in side))
    return clip_lines("\n".join(lines))


def trace_text(store: OpsStore, wave_id: str | None = None, max_lines: int = 34) -> str:
    """Cây vết dạng chữ của một đợt (lệnh `/trace`); bỏ trống thì lấy đợt gần nhất.

    Args:
        store: Store vận hành.
        wave_id: Mã đợt.
        max_lines: Số dòng tối đa.

    Returns:
        Văn bản nhiều dòng.
    """
    if not wave_id:
        latest = store.waves(1)
        if not latest:
            return "Chưa có đợt nào."
        wave_id = latest[0]["wave_id"]
    tr = sv.trace_of(store, wave_id)
    if not tr["spans"]:
        return f"Đợt {wave_id} chưa có span nào."
    by = {s["span_id"]: s for s in tr["spans"]}
    kids: dict = {}
    for s in tr["spans"]:
        kids.setdefault(s["parent_id"] if s["parent_id"] in by else "", []).append(s)
    order: list = []
    depth: dict = {}

    def walk(s, d: int) -> None:
        order.append(s)
        depth[s["span_id"]] = d
        for k in kids.get(s["span_id"], []):
            walk(k, d + 1)

    for root in kids.get("", []):
        walk(root, 0)
    lines = [f"Cây vết {wave_id} · {fmt_duration(tr['duration_ms'] / 1000)}"]
    for s in order[:max_lines]:
        t = f" · {fmt_int(s['tokens'])} token" if s["tokens"] else ""
        a = s["attrs"]
        note = f" · nhận {a['received']}/{a['total']}" if a.get("received") is not None else ""
        lines.append(f"{'  ' * depth[s['span_id']]}{s['name']} [{s['actor_id'] or s['kind']}] "
                     f"{fmt_duration(s['duration_ms'] / 1000)}{t}{note} · "
                     f"{label(SPAN_STATUS, s['status'])}")
    if len(order) > max_lines:
        lines.append(f"... còn {len(order) - max_lines} span (xem Phòng điều khiển)")
    return clip_lines("\n".join(lines))


def agent_text(store: OpsStore, agent_id: str) -> str:
    """Đặc tả và KPI 7 ngày của một tác nhân (lệnh `/agent`).

    Args:
        store: Store vận hành.
        agent_id: Mã tác nhân.

    Returns:
        Văn bản nhiều dòng.
    """
    card = sv.agent_card(store, agent_id)
    if not card:
        ids = ", ".join(sorted(a for a, v in sv.registry().items() if v.get("status") != "retired"))
        return f"Không có tác nhân {agent_id}. Có: {ids}"
    sp = card["spec"]
    io = sp.get("io_boundary") or {}
    lines = [f"{sp['id']} [{sp.get('class')}] {sp.get('status')}",
             f"Mô hình: {sp.get('model') or 'không dùng LLM'} · skill: {sp.get('skill') or '–'}",
             f"Công cụ cho phép: {', '.join(sp.get('tools_allowed') or []) or 'không có'}",
             f"Đọc: {'; '.join(io['read']) or 'không có' if 'read' in io else '–'}",
             f"Ghi: {'; '.join(io['write']) or 'không có' if 'write' in io else '–'}"]
    for t in card["trend"][-7:]:
        lat = f" · trung bình {fmt_duration(t['avg_latency_s'])}" if t["avg_latency_s"] else ""
        lines.append(f"{fmt_date(t['day'])}: {t['spans']} span · thành công {fmt_pct(t['success_rate'])}"
                     f" · {fmt_int(t['tokens'])} token{lat}")
    if not card["trend"]:
        lines.append("7 ngày qua: chưa có span.")
    if card["violations"]:
        lines.append(f"VI PHẠM công cụ: {len(card['violations'])} span")
    return clip_lines("\n".join(lines))


def improve_text(store: OpsStore) -> tuple[str, list[list[tuple[str, str]]]]:
    """Hộp thư cải tiến cho Telegram: tối đa 3 đề xuất mở kèm nút quyết định.

    Args:
        store: Store vận hành.

    Returns:
        Cặp (văn bản, hàng nút).
    """
    open_p = sv.proposals(store, "open", 3)
    if not open_p:
        return "Hộp thư cải tiến trống: chưa có đề xuất nào đủ bằng chứng.", []
    lines, buttons = ["Đề xuất cải tiến đang mở:"], []
    for p in open_p:
        lines.append(f"#{p['id']} {p['title']}\n   {p['kind']} · tác động {fmt_int(p['impact'])}")
        buttons.append([(f"Mở story #{p['id']}", f"/prop open_story {p['id']}"),
                        ("Hoãn 30 ngày", f"/prop defer {p['id']}"),
                        ("Bác 30 ngày", f"/prop reject {p['id']}")])
    return "\n".join(lines), buttons
