"""Kế thừa kết quả phân tích từ bài gốc cho bài chép lại trong cùng cụm (ADR 0016)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))
INHERITED = "inherited"
HOLD_HOURS = 48          # bài chép chờ bài gốc tối đa ngần này giờ rồi được trả về bộ chọn bài

_PASSING_L1 = "dod_pass = 1 AND COALESCE(l1_source, 'agent') <> 'code_first'"


def _loads(raw: str | None) -> dict:
    try:
        val = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}
    return val if isinstance(val, dict) else {}


def hold_cutoff(now: datetime | None = None) -> str:
    """Trả mốc thời gian ISO mà bài chép quyết định sau đó còn bị giữ lại chờ kế thừa.

    Args:
        now: Thời điểm hiện tại; mặc định lấy từ đồng hồ.

    Returns:
        Chuỗi ISO có múi giờ +07:00, cùng định dạng với `cluster_members.decided_at`.
    """
    now = now or datetime.now(VN_TZ)
    return (now - timedelta(hours=HOLD_HOURS)).isoformat(timespec="seconds")


def apply_inheritance(conn: sqlite3.Connection, now: datetime | None = None) -> dict[str, int]:
    """Ghi kết quả kế thừa cho mọi bài `copy` mà bài gốc đã có kết quả đạt chuẩn.

    Chỉ ghi khi bài chép chưa có kết quả mô hình đạt chuẩn và bài gốc có đủ hai lớp
    (nhận diện và nội dung) đạt cổng DoD. Dòng ghi mang `l1_source = 'inherited'`.

    Args:
        conn: Kết nối ghi tới DB vận hành, row_factory là sqlite3.Row hoặc tuple.
        now: Thời điểm hiện tại; mặc định lấy từ đồng hồ.

    Returns:
        Đếm: candidates, inherited, source_not_ready.
    """
    now_iso = (now or datetime.now(VN_TZ)).isoformat(timespec="seconds")
    stats = {"candidates": 0, "inherited": 0, "source_not_ready": 0}
    todo = conn.execute(
        "SELECT cm.article_id, json_extract(cm.evidence, '$.inherit_from') AS src, a.title "
        "FROM cluster_members cm JOIN articles a ON a.url_title_hash = cm.article_id "
        "WHERE cm.role = 'copy' AND NOT EXISTS ("
        f"  SELECT 1 FROM l1_outputs o WHERE o.article_id = cm.article_id AND o.{_PASSING_L1})"
    ).fetchall()
    stats["candidates"] = len(todo)
    for row in todo:
        article_id, src, title = row[0], row[1], row[2]
        l1 = conn.execute(
            f"SELECT output_json, recognized, model_used, confidence FROM l1_outputs "
            f"WHERE article_id = ? AND {_PASSING_L1}", (src,)).fetchone()
        ag = conn.execute(
            "SELECT output_json, model_used, confidence FROM agent_outputs "
            "WHERE article_id = ? AND dod_pass = 1 ORDER BY id DESC LIMIT 1", (src,)).fetchone()
        if l1 is None or ag is None:
            stats["source_not_ready"] += 1
            continue
        l1_doc = _loads(l1[0])
        l1_doc.update({"article_id": article_id, "title": title, "inherited_from": src})
        meta = l1_doc.setdefault("processing_metadata", {})
        meta.update({"agent_provider": INHERITED, "inherited_from": src, "timestamp": now_iso})
        ag_doc = _loads(ag[0])
        ag_doc.update({"article_id": article_id, "inherited_from": src})
        sha = conn.execute(
            "SELECT content_sha256 FROM article_versions WHERE url_title_hash = ? "
            "ORDER BY captured_at DESC, id DESC LIMIT 1", (article_id,)).fetchone()
        conn.execute(
            "INSERT OR REPLACE INTO l1_outputs (article_id, output_json, recognized, agent_provider, "
            "model_used, confidence, dod_pass, dod_reasons, created_at, l1_source) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
            (article_id, json.dumps(l1_doc, ensure_ascii=False), l1[1], INHERITED, l1[2], l1[3],
             f"inherited_from={src}", now_iso, INHERITED))
        conn.execute(
            "INSERT OR REPLACE INTO agent_outputs (article_id, raw_sha256, work_item_id, output_json, "
            "agent_provider, model_used, confidence, dod_pass, dod_reasons, created_at) "
            "VALUES (?, ?, NULL, ?, ?, ?, ?, 1, ?, ?)",
            (article_id, (sha[0] if sha and sha[0] else ""), json.dumps(ag_doc, ensure_ascii=False),
             INHERITED, ag[1], ag[2], f"inherited_from={src}", now_iso))
        stats["inherited"] += 1
    conn.commit()
    return stats
