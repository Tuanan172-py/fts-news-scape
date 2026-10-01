"""Phát hiện cơ hội cải tiến từ vết và KPI, rồi quản lý hộp thư đề xuất cho người duyệt."""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from typing import Callable

from src.ops import supervision as sv
from src.ops.store import OpsStore, iso, now_vn

REPO_ROOT = Path(__file__).resolve().parents[3]
MAX_PER_WEEK = 5
RESURFACE_DAYS = 30
MIN_WAVES = 3
INVARIANT_IMPACT = 1_000_000_000  # vi phạm bất biến luôn xếp trên mọi đề xuất tiết kiệm


def _mean(xs: list[float]) -> float:
    return statistics.fmean(xs) if xs else 0.0


def detect(store: OpsStore, cfg: dict) -> list[dict]:
    """Chạy các bộ phát hiện tất định (0 token) và trả về ứng viên đề xuất.

    Args:
        store: Store vận hành.
        cfg: Cấu hình đầy đủ.

    Returns:
        Danh sách {dedup_key, kind, title, evidence, impact}, chưa lọc trùng.
    """
    out: list[dict] = []
    ws = [w for w in sv.waves(store, 100) if w["status"] == "DONE" and w["n_articles"]]
    since = (now_vn() - timedelta(days=14)).date().isoformat()
    recent = [w for w in ws if w["opened_at"][:10] >= since]

    # 1. Lượt phân tích đầu thiếu bài nên bước vá tốn token.
    yields = [w["first_pass_yield"] for w in recent if w["first_pass_yield"] is not None]
    shares = [w["repair_share"] for w in recent if w["repair_share"] is not None]
    if len(yields) >= MIN_WAVES and (_mean(yields) < 0.8 or _mean(shares) > 0.3):
        rep_tokens = _mean([w["repair_tokens"] for w in recent])
        out.append({
            "dedup_key": "first_pass_yield_low", "kind": "yield",
            "title": (f"Lượt phân tích đầu chỉ nhận {_mean(yields):.0%} bài; bước vá tốn "
                      f"{_mean(shares):.0%} token của đợt"),
            "evidence": {"waves": len(yields), "mean_first_pass_yield": round(_mean(yields), 3),
                         "mean_repair_share": round(_mean(shares), 3),
                         "mean_repair_tokens_per_wave": round(rep_tokens)},
            "impact": round(rep_tokens)})

    # 2. Bộ nhớ đệm không được dùng lại giữa các tiến trình agy.
    ag = sv._rows(store, "SELECT attrs_json FROM ops_spans WHERE kind = 'agent' AND started_at >= ?",
                  (since,))
    usages = [sv._attrs(a).get("usage") or {} for a in ag]
    usages = [u for u in usages if u.get("input_tokens")]
    if len(usages) >= 4 and all(not u.get("cache_read_tokens") for u in usages):
        mean_in = _mean([u["input_tokens"] for u in usages])
        out.append({
            "dedup_key": "cache_never_hit", "kind": "cache",
            "title": "Bộ nhớ đệm của nhà cung cấp không được dùng lại giữa các lượt agy",
            "evidence": {"agent_spans": len(usages), "mean_input_tokens": round(mean_in),
                         "cache_read_tokens": 0},
            "impact": round(mean_in * len(usages) / max(1, len(recent)))})

    # 3. Vi phạm bất biến Zero-Tool.
    viol = [r for r in sv._rows(store, "SELECT span_id, trace_id, attrs_json FROM ops_spans "
                                       "WHERE kind = 'agent' AND started_at >= ?", (since,))
            if sv._attrs(r).get("tool_invoked") or sv._attrs(r).get("denied_actions")]
    if viol:
        out.append({"dedup_key": "tool_violation", "kind": "invariant",
                    "title": f"{len(viol)} lô agy có lượt gọi công cụ trái bất biến Zero-Tool",
                    "evidence": {"spans": [v["span_id"] for v in viol[:5]]},
                    "impact": INVARIANT_IMPACT})

    # 4. Breaker mở lặp lại.
    br_events = sv._rows(store, "SELECT message FROM ops_events WHERE kind = 'breaker.opened' "
                                "AND ts >= ?", (iso(now_vn() - timedelta(days=7)),))
    if len(br_events) >= 2:
        out.append({"dedup_key": "breaker_repeated", "kind": "provider",
                    "title": f"Breaker provider mở {len(br_events)} lần trong 7 ngày",
                    "evidence": {"count": len(br_events),
                                 "samples": [e["message"][:120] for e in br_events[:3]]},
                    "impact": 100 * len(br_events)})

    # 5. Bài hết lượt thử mà chưa qua DoD.
    n_attempts = int(cfg["wave"]["max_attempts_per_article"])
    stuck = sv._rows(store, "SELECT article_id FROM ops_article_attempts WHERE attempts >= ?",
                     (n_attempts,))
    done_ids = {r["article_id"] for r in sv._rows(
        store, "SELECT DISTINCT a.article_id FROM ops_wave_articles a JOIN ops_waves w "
               "ON w.wave_id = a.wave_id WHERE w.status = 'DONE'")}
    stuck_ids = [r["article_id"] for r in stuck if r["article_id"] not in done_ids]
    if len(stuck_ids) >= 5:
        out.append({"dedup_key": "poison_articles", "kind": "quality",
                    "title": f"{len(stuck_ids)} bài đã hết lượt thử mà chưa nạp được",
                    "evidence": {"count": len(stuck_ids), "sample": stuck_ids[:5]},
                    "impact": len(stuck_ids)})

    # 6. Dead-letter Bronze tăng.
    dl = sv._rows(store, "SELECT message FROM ops_events WHERE kind = 'probe.dead_letter.failed' "
                         "AND ts >= ? ORDER BY id DESC LIMIT 1", (iso(now_vn() - timedelta(days=7)),))
    if dl:
        out.append({"dedup_key": "dead_letter_growth", "kind": "capture",
                    "title": "Bronze dead-letter tăng quá ngưỡng trong ngày",
                    "evidence": {"message": dl[0]["message"][:200]}, "impact": 50})
    return out


def sync(store: OpsStore, cfg: dict, now=None) -> list[int]:
    """Thêm ứng viên mới vào hộp thư, bỏ trùng và giữ trần số đề xuất mỗi tuần (D-E).

    Đề xuất đã Hoãn hoặc Bác không xuất hiện lại trong `RESURFACE_DAYS` ngày.

    Args:
        store: Store vận hành.
        cfg: Cấu hình đầy đủ.
        now: Thời điểm tham chiếu, dùng cho kiểm thử.

    Returns:
        Mã các đề xuất mới.
    """
    now = now or now_vn()
    cap = int(cfg.get("improvement", {}).get("max_per_week", MAX_PER_WEEK))
    week = iso(now - timedelta(days=7))
    month = iso(now - timedelta(days=RESURFACE_DAYS))
    new_ids: list[int] = []
    for cand in sorted(detect(store, cfg), key=lambda c: -c["impact"]):
        with store.conn() as c:
            made = c.execute("SELECT COUNT(*) FROM ops_proposals WHERE created_at >= ?",
                             (week,)).fetchone()[0]
            if made >= cap:
                break
            dup = c.execute(
                "SELECT 1 FROM ops_proposals WHERE dedup_key = ? AND (status = 'open' OR created_at >= ? "
                "OR (status IN ('deferred','rejected') AND decided_at >= ?)) LIMIT 1",
                (cand["dedup_key"], week, month)).fetchone()
            if dup:
                continue
            cur = c.execute(
                "INSERT INTO ops_proposals(created_at, dedup_key, kind, title, evidence_json, impact) "
                "VALUES (?,?,?,?,?,?)",
                (iso(now), cand["dedup_key"], cand["kind"], cand["title"],
                 json.dumps(cand["evidence"], ensure_ascii=False), cand["impact"]))
            new_ids.append(int(cur.lastrowid))
        store.emit("proposal.created", cand["title"], actor="daemon",
                   data={"id": new_ids[-1], "kind": cand["kind"], "impact": cand["impact"]})
    return new_ids


def _harness(*args: str) -> subprocess.CompletedProcess:
    """Gọi `scripts/harness_cli.py` từ gốc kho với đường dẫn mặc định của harness."""
    return subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "harness_cli.py"), *args],
                          cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)


def decide(store: OpsStore, proposal_id: int, action: str, *, actor: str = "human",
           harness: Callable[..., subprocess.CompletedProcess] = _harness) -> dict:
    """Ghi quyết định của người với một đề xuất; chỉ `open_story` đi vào quy trình story.

    Đề xuất tự sinh không bao giờ tự thi hành: người chọn Mở story thì mới có intake và
    story ở trạng thái `planned`, còn mọi thay đổi mã đi qua quy trình thường của repo.

    Args:
        store: Store vận hành.
        proposal_id: Mã đề xuất.
        action: `open_story`, `defer` hoặc `reject`.
        actor: Nguồn quyết định (web, telegram).
        harness: Hàm gọi harness CLI, thay được trong kiểm thử.

    Returns:
        Từ điển {ok, status, story_id, message}.
    """
    with store.conn() as c:
        row = c.execute("SELECT * FROM ops_proposals WHERE id = ?", (proposal_id,)).fetchone()
    if row is None:
        return {"ok": False, "message": f"Không có đề xuất {proposal_id}."}
    if row["status"] != "open":
        return {"ok": False, "status": row["status"], "message": f"Đề xuất đã ở trạng thái {row['status']}."}
    story_id = None
    if action == "open_story":
        story_id = f"US-IMP-{proposal_id:03d}"
        ev = row["evidence_json"] or "{}"
        r1 = harness("intake", "--type", "harness_improvement", "--lane", "normal",
                     "--summary", row["title"][:200])
        r2 = harness("story", "add", "--id", story_id, "--title", row["title"][:200],
                     "--parent", "Autonomous Ops", "--lane", "normal", "--status", "planned",
                     "--contract", "Đề xuất cải tiến tự sinh từ vết vận hành, người vận hành đã duyệt mở story",
                     "--criteria", f"Bằng chứng: {ev[:400]}")
        if r1.returncode != 0 or r2.returncode != 0:
            msg = (r2.stderr or r2.stdout or r1.stderr or r1.stdout or "")[-300:]
            store.emit("proposal.story_failed", f"{story_id}: {msg}", level="warn", actor=actor)
            return {"ok": False, "message": f"Không tạo được story: {msg}"}
        status = "story_opened"
    elif action == "defer":
        status = "deferred"
    elif action == "reject":
        status = "rejected"
    else:
        return {"ok": False, "message": f"Hành động không hợp lệ: {action}."}
    with store.conn() as c:
        c.execute("UPDATE ops_proposals SET status = ?, decided_at = ?, story_id = ? WHERE id = ?",
                  (status, iso(), story_id, proposal_id))
    store.emit("proposal.decided", f"#{proposal_id} → {status}", actor="human",
               data={"id": proposal_id, "action": action, "source": actor, "story_id": story_id})
    return {"ok": True, "status": status, "story_id": story_id,
            "message": (f"Đã mở story {story_id}." if story_id else f"Đã {action} đề xuất #{proposal_id}.")}
