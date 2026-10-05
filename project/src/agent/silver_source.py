"""Định vị và đọc thân bài tầng Silver cho Article Lane.

Packet và gói công việc phải dùng cùng một thân bài mà trích dẫn sẽ đối chiếu vào:
thân bài đầy đủ từ Silver, không phải đoạn trích RSS ngắn. Mọi nơi cần thân bài
đều đi qua đây để không ai đọc lệch nguồn.
"""
from __future__ import annotations

import json
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
SILVER_ROOT = _PROJECT_ROOT / "data" / "silver"


def silver_package_path(source_domain: str | None, published_at: str | None,
                         article_id: str) -> Path | None:
    """Dựng đường dẫn gói Silver từ định danh bài.

    Bố cục kho Silver là `data/silver/<domain>/<yyyymmdd>/<hash>.json`. Ngày lấy
    từ 10 ký tự đầu của `published_at`, bỏ dấu gạch.

    Args:
        source_domain: Tên miền nguồn, ví dụ `vneconomy.vn`.
        published_at: Mốc xuất bản, ví dụ `2026-10-05T...`.
        article_id: Băm định danh bài (`url_title_hash`).

    Returns:
        Đường dẫn gói khi tệp tồn tại, None khi thiếu dữ kiện hoặc không thấy tệp.
    """
    try:
        if not source_domain or not published_at or not article_id:
            return None
        day = (published_at or "")[:10].replace("-", "")
        if len(day) != 8 or not day.isdigit():
            return None
        candidate = SILVER_ROOT / source_domain / day / f"{article_id}.json"
        return candidate if candidate.is_file() else None
    except (TypeError, ValueError, OSError):
        return None


def read_silver_text(source_domain: str | None, published_at: str | None,
                      article_id: str) -> str:
    """Đọc trường `cleaned_text` của gói Silver.

    Args:
        source_domain: Tên miền nguồn.
        published_at: Mốc xuất bản.
        article_id: Băm định danh bài.

    Returns:
        Thân bài đầy đủ, hoặc chuỗi rỗng khi không có gói Silver đọc được.
    """
    path = silver_package_path(source_domain, published_at, article_id)
    if path is None:
        return ""
    try:
        return (json.loads(path.read_text(encoding="utf-8")) or {}).get("cleaned_text") or ""
    except (OSError, ValueError):
        return ""
