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

_SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"
OUTPUT_SCHEMA = "agent-output-v1"
_OUTPUT_REQUIRED = [
    "output_schema_version", "article_id", "summary", "implication",
    "materiality", "confidence", "citations", "processing_metadata",
]


def build_task_packet(work_package: dict, *, work_item_id: int | None = None) -> dict:
    """Gộp work-package + hợp đồng output + ràng buộc thành 1 packet self-describing."""
    t = load_thresholds()
    return {
        "packet_version": "1.0",
        "work_item_id": work_item_id,
        "article_id": work_package.get("article_id"),
        "raw_sha256": work_package.get("raw_sha256"),
        # INPUT — agent đọc cleaned_text; verify raw_sha256 trước khi xử lý.
        "input": work_package,
        # OUTPUT contract — agent PHẢI emit đúng schema này.
        "output_contract": {
            "schema_name": OUTPUT_SCHEMA,
            "schema_path": f"schemas/{OUTPUT_SCHEMA}.schema.json",
            "required": _OUTPUT_REQUIRED,
            "thinking_order": ["summary(tóm tắt)", "implication(hàm ý)", "materiality(mức độ quan trọng)"],
        },
        # Ràng buộc để agent tự canh trước khi nộp (khớp DoD ở ingest).
        "constraints": {
            "confidence_min": t["confidence_min"],
            "min_citations": t["min_citations"],
            "citations_must_be_substring_of": "input.cleaned_text",
            "extraction_quality_in": list(t["quality_ok"]),
            "processing_metadata_required": ["agent_provider", "model_used", "timestamp"],
            "preconditions": [
                "verify sha256(raw_html_path) == raw_sha256",
                "skip if change_state in [SELECTOR_BROKEN, TEMPLATE_DRIFT]",
            ],
        },
        "instructions_ref": "schemas/agent-instructions-v1.md",
    }


def write_packet(packet: dict, base_dir: str = "data/agent_tasks") -> str:
    """Ghi packet ra đĩa (atomic). Trả path."""
    os.makedirs(base_dir, exist_ok=True)
    path = os.path.join(base_dir, f"{packet['article_id']}.task.json")
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(packet, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path
