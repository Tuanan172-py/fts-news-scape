"""Chạy cụm hoá trùng lặp rồi ghi kết quả kế thừa trong một bước, 0 token."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from src.pipeline import story_cluster
from src.pipeline.inherit import apply_inheritance


def refresh(conn: sqlite3.Connection, days: int = 3,
            today: datetime | None = None) -> dict[str, int]:
    """Cụm hoá các ngày gần nhất rồi ghi kết quả kế thừa.

    Args:
        conn: Kết nối ghi tới DB vận hành.
        days: Số ngày gần nhất cần cụm hoá, tính cả hôm nay.
        today: Mốc "hôm nay" của cửa sổ cụm hoá và kế thừa; None là giờ hiện tại.

    Returns:
        Từ điển gộp thống kê cụm hoá và kế thừa; khoá kế thừa có tiền tố `inherit_`.
    """
    stats = story_cluster.run(conn, days=days, today=today)
    inh = apply_inheritance(conn, now=today)
    return {**stats, **{f"inherit_{k}": v for k, v in inh.items()}}
