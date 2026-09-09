# -*- coding: utf-8 -*-
"""
L1 matcher — MỎNG, uỷ quyền hoàn toàn về đường tất định canonical.

Trước 2026-09-09 file này chứa một BỘ KHỚP THỨ HAI (`match_entities_in_title`, ~137 dòng) với
danh sách guard hard-code riêng (`quy`/`dau`/`ban`/`my`/`eu`/`us`), bảng `GLOBAL_UNLISTED_ENTITIES`
tự biên, và `build_l1_output` đóng dấu `agent_provider="gemini"`, `model_used="flash"` cùng một
timestamp cố định — tức script tự sinh kết quả rồi khai provenance LLM. Hai hệ quả:

  1. Trôi khác `EntityRegistry.detect()`: bản canonical đã có guard ngữ cảnh, khử chồng lấn tên
     công ty và stoplist alias chung, còn bản này thì không → hai nơi cho hai kết quả khác nhau.
  2. Provenance giả — đúng mẫu vi phạm AGENTS.md §6.C mà ADR 0004 chỉ ra (1.117/1.274 bản ghi
     Gold từng là sản phẩm regex nhưng mang nhãn LLM).

Nay chỉ còn lớp vỏ để `scripts/run_validation.py` giữ nguyên chỗ gọi. Nhận diện thực thể dùng
`classify_title` (EntityRegistry), đóng gói dùng `build_code_first_output` — nên output khai
đúng nguồn `code_first` / `deterministic`. Việc nhận diện NGỮ NGHĨA (thực thể ngoài danh mục,
suy luận ngữ cảnh) vẫn là vùng độc quyền của Subagent L1.
"""
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
    """1 task L1 (`article_id` + `title`) → `l1-entity-output-v1`.

    KHÔNG đọc `task["code_first"]` đã đóng gói sẵn: chạy lại matcher hiện hành trên tiêu đề để
    kiểm định đúng hành vi ĐANG chạy của pipeline, thay vì hành vi lúc gói được tạo ra.
    """
    rec = classify_title(task["title"])
    return build_code_first_output(rec, task["article_id"])
