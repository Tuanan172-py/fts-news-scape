"""Quản lý điểm kiểm tra (checkpoint) tiến trình xuất dữ liệu cho người dùng."""
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
    """Đọc dữ liệu điểm kiểm tra của người dùng từ đĩa.

    Args:
        user_dir: Thư mục xuất dữ liệu của người dùng.

    Returns:
        Từ điển dữ liệu điểm kiểm tra gồm danh sách bài đã ghi và mốc thời gian chạy.
    """
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
    """Lấy danh sách bản ghi bài viết kèm trạng thái xử lý theo ngày.

    Args:
        user_dir: Thư mục xuất dữ liệu của người dùng.
        date: Ngày xuất bản dạng 'YYYY-MM-DD'.

    Returns:
        Từ điển ánh xạ mã bài viết sang trạng thái phân tích ('GOLD' hoặc 'L1_ONLY').
    """
    raw = load_checkpoint(user_dir).get("written", {}).get(date, {})
    if isinstance(raw, dict):
        return {str(k): str(v or "") for k, v in raw.items()}
    return {str(aid): "" for aid in (raw or [])}             # định dạng cũ


def written_ids(user_dir: str | Path, date: str) -> set[str]:
    """Lấy tập hợp các mã bài viết đã được ghi nhận trong ngày.

    Args:
        user_dir: Thư mục xuất dữ liệu của người dùng.
        date: Ngày xuất bản dạng 'YYYY-MM-DD'.

    Returns:
        Tập hợp các mã bài viết đã ghi.
    """
    return set(_entries(user_dir, date))


def filter_new(user_dir: str | Path, date: str, article_ids) -> list[str]:
    """Lọc danh sách các mã bài viết mới chưa từng được xuất trong ngày.

    Args:
        user_dir: Thư mục xuất dữ liệu của người dùng.
        date: Ngày xuất bản dạng 'YYYY-MM-DD'.
        article_ids: Danh sách mã bài viết cần kiểm tra.

    Returns:
        Danh sách mã bài viết mới chưa xuất hiện trong điểm kiểm tra.
    """
    seen = written_ids(user_dir, date)
    out, dedup = [], set()
    for aid in article_ids:
        if aid not in seen and aid not in dedup:
            dedup.add(aid); out.append(aid)
    return out


def filter_upgraded(user_dir: str | Path, date: str, statuses: dict[str, str]) -> list[str]:
    """Lọc các bài viết được nâng cấp trạng thái từ L1_ONLY lên GOLD.

    Args:
        user_dir: Thư mục xuất dữ liệu của người dùng.
        date: Ngày xuất bản dạng 'YYYY-MM-DD'.
        statuses: Từ điển trạng thái hiện tại của các bài viết.

    Returns:
        Danh sách mã bài viết vừa được bổ sung phân tích chuyên sâu Gold.
    """
    prev = _entries(user_dir, date)
    return [aid for aid, st in statuses.items()
            if prev.get(aid) == "L1_ONLY" and st == "GOLD"]


def mark_written(user_dir: str | Path, date: str, article_ids, statuses=None) -> bool:
    """Cập nhật trạng thái các bài viết đã xuất vào tệp điểm kiểm tra.

    Args:
        user_dir: Thư mục xuất dữ liệu của người dùng.
        date: Ngày xuất bản dạng 'YYYY-MM-DD'.
        article_ids: Danh sách các mã bài viết đã ghi thành công.
        statuses: Từ điển trạng thái tương ứng của từng bài viết tùy chọn.

    Returns:
        True nếu lưu thành công, False nếu tệp bị khóa.
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
