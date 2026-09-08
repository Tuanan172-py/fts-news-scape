"""
Task-packet builder — gói 1 công việc để giao cho agent NGOÀI (do người dùng điều khiển).

Packet tự mô tả, đủ để bất kỳ agent/prompt nào xử lý mà KHÔNG cần biết nội bộ codebase:
- input          : work-package-v1 (đã trỏ raw, có cleaned_text)
- output_contract: tên schema + đường dẫn + required fields (agent PHẢI emit đúng)
- constraints    : ngưỡng DoD + preconditions (để agent tự canh)
- instructions   : trỏ tới schemas/agent-instructions-v1.md (người dùng viết prompt từ đây)

KHÔNG chứa lời gọi LLM. Ghi ra data/agent_tasks/<article_id>.task.json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from src.agent.dod import load_thresholds
from src.agent.pruner import clean_article_paragraphs

_SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"
OUTPUT_SCHEMA = "agent-output-v1"
_OUTPUT_REQUIRED = [
    "output_schema_version", "article_id", "summary", "implication",
    "materiality", "citations", "processing_metadata",
]


def build_gold_input(work_package: dict, *, l1_entities: list[str] | None = None, prune: bool = True) -> dict:
    """Tạo payload input tinh gọn (Zero-Waste), loại bỏ 100% links/images/table rác."""
    raw_text = work_package.get("cleaned_text", "") or ""
    cleaned_text = clean_article_paragraphs(raw_text) if prune else raw_text

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
    struct = work_package.get("structure")
    if isinstance(struct, dict) and "headings" in struct:
        inp["structure"] = {"headings": struct.get("headings", [])}

    if l1_entities is not None:
        inp["l1_entities"] = l1_entities
    return inp


def build_task_packet(
    work_package: dict,
    *,
    work_item_id: int | None = None,
    l1_entities: list[str] | None = None,
    prune: bool = True,
) -> dict:
    """Gộp work-package tinh gọn + hợp đồng output + ràng buộc thành 1 packet self-describing."""
    t = load_thresholds()
    gold_input = build_gold_input(work_package, l1_entities=l1_entities, prune=prune)
    return {
        "packet_version": "1.0",
        "work_item_id": work_item_id,
        "article_id": work_package.get("article_id"),
        "raw_sha256": work_package.get("raw_sha256"),
        # INPUT — agent đọc cleaned_text sạch (đã prune, loại bỏ boilerplate)
        "input": gold_input,
        # OUTPUT contract — agent PHẢI emit đúng schema này.
        "output_contract": {
            "schema_name": OUTPUT_SCHEMA,
            "schema_path": f"schemas/{OUTPUT_SCHEMA}.schema.json",
            "required": _OUTPUT_REQUIRED,
            "thinking_order": ["summary(tóm tắt)", "implication(hàm ý)", "materiality(mức độ quan trọng)"],
        },
        # Ràng buộc để agent tự canh trước khi nộp (khớp DoD ở ingest).
        "constraints": {
            "min_citations": t["min_citations"],
            "citations_must_be_substring_of": "input.cleaned_text",
            "min_citation_len": 20,
            "extraction_quality_in": list(t["quality_ok"]),
            "processing_metadata_required": ["agent_provider", "model_used", "timestamp"],
            "preconditions": [
                "verify sha256(raw_html_path) == raw_sha256",
                "skip if change_state in [SELECTOR_BROKEN, TEMPLATE_DRIFT]",
            ],
        },
        "instructions_ref": "schemas/agent-instructions-v1.md",
    }


from src.core.staging import safe_json_dump


def write_packet(packet: dict, base_dir: str = "data/agent_tasks") -> str:
    """Ghi packet ra đĩa an toàn qua staging (atomic). Trả path."""
    os.makedirs(base_dir, exist_ok=True)
    target_path = os.path.join(base_dir, f"{packet['article_id']}.task.json")
    final_path, _ = safe_json_dump(packet, target_path, indent=2)
    return str(final_path)
