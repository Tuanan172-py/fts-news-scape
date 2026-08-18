"""
checkpoint.py — Trạng thái resume per-user cho output (idempotent theo article_id).

File: `users/output/<name>/_checkpoint.json`
    { "written": { "2026-08-18": ["<article_id>", ...] }, "last_run_at": ..., "last_date": ... }

Nguyên tắc crash-safe: GHI file output trước (atomic os.replace) → RỒI mới mark checkpoint.
Nếu chết giữa chừng, lần chạy sau ghi lại (rewrite toàn tập) nên không trùng, không mất.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from src.core.models import now_vn_iso

CHECKPOINT_NAME = "_checkpoint.json"


def _path(user_dir: str | Path) -> Path:
    return Path(user_dir) / CHECKPOINT_NAME


def load_checkpoint(user_dir: str | Path) -> dict:
    p = _path(user_dir)
    if not p.exists():
        return {"written": {}, "last_run_at": None, "last_date": None}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"written": {}, "last_run_at": None, "last_date": None}
    data.setdefault("written", {})
    return data


def written_ids(user_dir: str | Path, date: str) -> set[str]:
    return set(load_checkpoint(user_dir).get("written", {}).get(date, []))


def filter_new(user_dir: str | Path, date: str, article_ids) -> list[str]:
    """Trả article_id CHƯA ghi cho ngày `date` (để log số mới; không loại khỏi output)."""
    seen = written_ids(user_dir, date)
    out, dedup = [], set()
    for aid in article_ids:
        if aid not in seen and aid not in dedup:
            dedup.add(aid); out.append(aid)
    return out


def mark_written(user_dir: str | Path, date: str, article_ids) -> None:
    """Cập nhật checkpoint SAU khi file output đã ghi thành công."""
    p = _path(user_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = load_checkpoint(user_dir)
    cur = set(data["written"].get(date, []))
    cur.update(article_ids)
    data["written"][date] = sorted(cur)
    data["last_run_at"] = now_vn_iso()
    data["last_date"] = date
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)
