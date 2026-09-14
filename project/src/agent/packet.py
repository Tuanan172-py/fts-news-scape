"""Đóng gói gói công việc giao tác vụ cho agent."""

from __future__ import annotations

import json
import os
from pathlib import Path

from src.agent.dod import load_thresholds
from src.agent.pruner import clean_article_paragraphs

_SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"
OUTPUT_SCHEMA = "agent-output-v2-lean"
_OUTPUT_REQUIRED_V2 = [
    "article_id", "summary", "key_points", "implication",
    "sentiment", "time_sensitivity", "citations",
]
_OUTPUT_REQUIRED_V1 = [
    "output_schema_version", "article_id", "summary", "implication",
    "materiality", "citations", "processing_metadata",
]
_OUTPUT_REQUIRED = _OUTPUT_REQUIRED_V2


def build_gold_input(work_package: dict, *, l1_entities: list[str] | None = None, prune: bool = True) -> dict:
    """Tạo payload dữ liệu đầu vào đã làm sạch cho tác vụ agent.

    Args:
        work_package: Gói công việc nguồn work-package-v1.
        l1_entities: Danh sách thực thể L1 đã nhận diện tùy chọn.
        prune: Có lọc bỏ văn bản rác và boilerplate hay không. Mặc định True.

    Returns:
        Từ điển dữ liệu đầu vào tinh gọn.
    """
    raw_text = work_package.get("cleaned_text", "") or ""
    cleaned_text = clean_article_paragraphs(raw_text, l1_entities=l1_entities) if prune else raw_text

    inp = {
        "article_id": work_package.get("article_id", ""),
        "source_url": work_package.get("source_url", ""),
        "domain": work_package.get("domain", ""),
        "published_at": work_package.get("published_at"),
        "raw_html_path": work_package.get("raw_html_path", ""),
        "raw_sha256": work_package.get("raw_sha256", ""),
        "title": work_package.get("title", ""),
        "cleaned_text": cleaned_text,
        "capture_status": work_package.get("capture_status", "ok"),
        "change_state": work_package.get("change_state", "OK"),
    }
    # Loại bỏ triệt để structure.headings để tránh lọt tiêu đề tin rác/sidebar gây tốn token và hallucinate

    if l1_entities is not None:
        inp["l1_entities"] = l1_entities
    return inp


def build_task_packet(
    work_package: dict,
    *,
    work_item_id: int | None = None,
    l1_entities: list[str] | None = None,
    prune: bool = True,
    schema_name: str = OUTPUT_SCHEMA,
) -> dict:
    """Đóng gói toàn diện gói công việc kèm hợp đồng dữ liệu đầu ra và ràng buộc.

    Args:
        work_package: Gói công việc nguồn chứa nội dung bài viết.
        work_item_id: Định danh bản ghi tác vụ trong hàng đợi xử lý.
        l1_entities: Danh sách thực thể L1 đã gắn thẻ.
        prune: Có lọc tỉa nội dung văn bản thừa hay không.
        schema_name: Tên lược đồ hợp đồng đầu ra (mặc định agent-output-v2-lean).

    Returns:
        Từ điển gói tác vụ đầy đủ tuân thủ hợp đồng giao tiếp agent.
    """
    t = load_thresholds()
    gold_input = build_gold_input(work_package, l1_entities=l1_entities, prune=prune)
    is_v1 = schema_name == "agent-output-v1"
    required_fields = _OUTPUT_REQUIRED_V1 if is_v1 else _OUTPUT_REQUIRED_V2

    constraints: dict = {
        "min_citations": t["min_citations"],
        "citations_must_be_substring_of": "input.cleaned_text",
        "min_citation_len": 20,
        "preconditions": [
            "verify sha256(raw_html_path) == raw_sha256",
            "skip if change_state in [SELECTOR_BROKEN, TEMPLATE_DRIFT]",
        ],
    }
    if is_v1:
        constraints["extraction_quality_in"] = list(t["quality_ok"])
        constraints["processing_metadata_required"] = ["agent_provider", "model_used", "timestamp"]
    else:
        constraints["citations_format"] = "array of verbatim strings (>= 20 chars each)"
        constraints["metadata_note"] = "Zero-token metadata: system auto-injects provider, model, timestamp at ingest"

    return {
        "packet_version": "2.0" if not is_v1 else "1.0",
        "work_item_id": work_item_id,
        "article_id": work_package.get("article_id"),
        "raw_sha256": work_package.get("raw_sha256"),
        # INPUT — agent đọc cleaned_text sạch (đã prune, loại bỏ boilerplate)
        "input": gold_input,
        # OUTPUT contract — agent PHẢI emit đúng schema này.
        "output_contract": {
            "schema_name": schema_name,
            "schema_path": f"schemas/{schema_name}.schema.json",
            "required": required_fields,
            "thinking_order": ["summary(tóm tắt)", "implication(hàm ý)", "sentiment", "time_sensitivity"],
        },
        # Ràng buộc để agent tự canh trước khi nộp (khớp DoD ở ingest).
        "constraints": constraints,
        "instructions_ref": "schemas/agent-instructions-v1.md",
    }


from src.core.staging import safe_json_dump


def write_packet(packet: dict, base_dir: str = "data/agent_tasks") -> str:
    """Lưu gói công việc ra đĩa an toàn qua cơ chế staging nguyên tử.

    Args:
        packet: Dữ liệu gói công việc cần ghi.
        base_dir: Thư mục gốc lưu trữ gói công việc.

    Returns:
        Đường dẫn tệp gói tác vụ đã ghi trên đĩa.
    """
    os.makedirs(base_dir, exist_ok=True)
    target_path = os.path.join(base_dir, f"{packet['article_id']}.task.json")
    final_path, _ = safe_json_dump(packet, target_path, indent=2)
    return str(final_path)
