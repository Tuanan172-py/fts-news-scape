"""
checkpoint.py — Trạng thái resume per-user cho output (idempotent theo article_id).

File: `users/output/<name>/_checkpoint.json`
    { "written": { "2026-08-18": {"<article_id>": "GOLD"|"L1_ONLY"} },
      "last_run_at": ..., "last_date": ... }

Nguyên tắc crash-safe: GHI file output trước (atomic os.replace) → RỒI mới mark checkpoint.
Nếu chết giữa chừng, lần chạy sau ghi lại (rewrite toàn tập) nên không trùng, không mất.

**Vai trò thật (rà 2026-09-07):** checkpoint KHÔNG quyết định nội dung output — idempotency đến
từ việc rewrite toàn tập + `os.replace` + dedupe theo `article_id`. Nó là **sổ cái "đã giao gì,
ở trạng thái nào"**: nguồn duy nhất trả lời "bài nào mới" và "bài nào vừa được Gold bổ sung".

Từ khi gate export nới thành L1-only, một bài có thể được giao ở trạng thái `L1_ONLY` rồi vòng
sau mới đầy đủ `GOLD`. Nếu chỉ lưu danh sách id thì "đã ghi" không còn đồng nghĩa "đã giao đủ" →
lưu kèm `gold_status` để phân biệt. Định dạng cũ (list id) vẫn đọc được, coi như status rỗng.

**Giới hạn (R1):** `mark_written` vẫn là read-modify-write, không có khoá liên tiến trình. Ghi file
đã atomic + tmp unique nên KHÔNG hỏng JSON nữa, nhưng hai run thật sự song song vẫn có thể
lost-update (bản ghi sau đè bản trước). Chống chồng run bằng `data/.pipeline.lock` ở run_daily.ps1.
"""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from src.core.models import now_vn_iso
from src.core.staging import safe_atomic_write

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


def _entries(user_dir: str | Path, date: str) -> dict[str, str]:
    """Bản ghi của 1 ngày dạng {article_id: gold_status}. Đọc được cả định dạng cũ (list id)."""
    raw = load_checkpoint(user_dir).get("written", {}).get(date, {})
    if isinstance(raw, dict):
        return {str(k): str(v or "") for k, v in raw.items()}
    return {str(aid): "" for aid in (raw or [])}             # định dạng cũ


def written_ids(user_dir: str | Path, date: str) -> set[str]:
    return set(_entries(user_dir, date))


def filter_new(user_dir: str | Path, date: str, article_ids) -> list[str]:
    """Trả article_id CHƯA ghi cho ngày `date` (để log số mới; không loại khỏi output)."""
    seen = written_ids(user_dir, date)
    out, dedup = [], set()
    for aid in article_ids:
        if aid not in seen and aid not in dedup:
            dedup.add(aid); out.append(aid)
    return out


def filter_upgraded(user_dir: str | Path, date: str, statuses: dict[str, str]) -> list[str]:
    """Bài ĐÃ giao trước đó ở trạng thái L1_ONLY mà lần này đã có Gold."""
    prev = _entries(user_dir, date)
    return [aid for aid, st in statuses.items()
            if prev.get(aid) == "L1_ONLY" and st == "GOLD"]


def mark_written(user_dir: str | Path, date: str, article_ids, statuses=None) -> bool:
    """Cập nhật checkpoint SAU khi file output đã ghi thành công.

    `statuses` = {article_id: gold_status}; thiếu thì ghi status rỗng (giữ tương thích lời gọi cũ).

    Trả True nếu ghi được sổ; False nếu file đang bị khoá — KHÔNG raise, để một user hỏng
    không làm chết cả vòng lặp ghi output của các user còn lại.
    """
    p = _path(user_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = load_checkpoint(user_dir)
    cur = _entries(user_dir, date)
    statuses = statuses or {}
    for aid in article_ids:
        cur[aid] = statuses.get(aid, cur.get(aid, ""))
    data["written"][date] = dict(sorted(cur.items()))
    data["last_run_at"] = now_vn_iso()
    data["last_date"] = date
    try:
        # safe_atomic_write dùng tmp tên unique (pid+uuid) → hai run song song không giẫm lên
        # nhau như tên tmp cố định `_checkpoint.json.tmp` trước đây.
        # fallback_on_lock=False: snapshot `_checkpoint_HHMMSS.json` vô nghĩa vì không ai đọc nó.
        safe_atomic_write(p, json.dumps(data, ensure_ascii=False, indent=2),
                          fallback_on_lock=False, encoding="utf-8")
        return True
    except OSError as e:
        logger.warning("checkpoint bị khoá, bỏ qua ghi sổ (user={} date={}): {}", p.parent.name, date, e)
        return False
