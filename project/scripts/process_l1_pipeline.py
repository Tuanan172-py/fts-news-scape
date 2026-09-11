"""Tiếp hợp phân loại thực thể tầng L1 cho bộ kiểm thử hợp chuẩn."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.l1_classifier import classify_title            # noqa: E402
from src.agent.l1_router import build_code_first_output       # noqa: E402
from src.agent.l1_router import check_l1_dod                  # noqa: E402,F401  (re-export)

__all__ = ["build_l1_output", "check_l1_dod"]


def build_l1_output(task: dict) -> dict:
    """Tạo kết quả phân loại L1 chuẩn từ tiêu đề bài viết trong gói công việc.

    Args:
        task: Từ điển gói công việc L1 chứa article_id và title.

    Returns:
        Từ điển kết quả thực thể tuân thủ schema l1-entity-output-v1.
    """
    rec = classify_title(task["title"])
    return build_code_first_output(rec, task["article_id"])
