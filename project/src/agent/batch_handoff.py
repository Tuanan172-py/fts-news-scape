"""Đóng gói và giải nén tác vụ xử lý theo lô gom nhóm (Batch Handoff).

Cung cấp các cơ chế gom nhiều bài viết thành một tệp gói tác vụ mini-batch duy nhất
cho Agent (tầng L1 hoặc Gold) và giải nén các tệp kết quả trả về.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.agent.dod import load_thresholds
from src.core.staging import safe_json_dump

OUTPUT_SCHEMA = "agent-output-v1"
_OUTPUT_REQUIRED = [
    "output_schema_version", "article_id", "summary", "implication",
    "materiality", "citations", "processing_metadata",
]


def build_batch_packet(tasks: list[dict], batch_id: str) -> dict:
    """Đóng gói danh sách gói tác vụ đơn lẻ thành một gói tác vụ lô (batch packet) tầng Gold.

    Args:
        tasks: Danh sách các gói tác vụ đơn lẻ cần gom nhóm.
        batch_id: Mã định danh của lô công việc (ví dụ: 'batch_01').

    Returns:
        Từ điển cấu trúc gói tác vụ gom lô tự mô tả.
    """
    t = load_thresholds()
    batch_tasks = []
    for tsk in tasks:
        inp = tsk.get("input", {})
        batch_tasks.append({
            "article_id": tsk.get("article_id") or inp.get("article_id", ""),
            "title": inp.get("title", ""),
            "domain": inp.get("domain", ""),
            "published_at": inp.get("published_at", ""),
            "cleaned_text": inp.get("cleaned_text", ""),
            "l1_entities": inp.get("l1_entities", []),
        })

    return {
        "packet_version": "1.0",
        "batch_id": batch_id,
        "task_count": len(batch_tasks),
        "tasks": batch_tasks,
        "output_contract": {
            "schema_name": OUTPUT_SCHEMA,
            "format": "JSON array of agent-output-v1 objects or {batch_id, outputs: [...]}",
            "required_fields_per_item": _OUTPUT_REQUIRED,
            "thinking_order": ["summary(tóm tắt)", "implication(hàm ý)", "materiality(mức độ quan trọng)"],
        },
        "constraints": {
            "min_citations": t["min_citations"],
            "citations_must_be_substring_of": "tasks[i].cleaned_text",
            "min_citation_len": 20,
            "extraction_quality_in": list(t["quality_ok"]),
            "processing_metadata_required": ["agent_provider", "model_used", "timestamp"],
        },
        "instructions_ref": "schemas/agent-instructions-v1.md",
    }


L1_OUTPUT_SCHEMA = "l1-entity-output-v1"
_L1_OUTPUT_REQUIRED = [
    "l1_output_version", "article_id", "title", "recognized",
    "entities", "categories", "citations", "processing_metadata",
]


def build_l1_batch_packet(tasks: list[dict], batch_id: str) -> dict:
    """Đóng gói danh sách bài viết thành gói tác vụ gom lô nhận diện thực thể tầng L1.

    Args:
        tasks: Danh sách các bài viết cần thẩm định nhận diện thực thể.
        batch_id: Mã định danh của lô công việc L1.

    Returns:
        Từ điển gói tác vụ gom lô tầng L1 kèm thông tin gợi ý code-first.
    """
    batch_tasks = []
    for tsk in tasks:
        inp = tsk.get("input", {})
        cf = tsk.get("code_first") or inp.get("code_first") or {}
        batch_tasks.append({
            "article_id": tsk.get("article_id") or inp.get("article_id", ""),
            "title": tsk.get("title") or inp.get("title", ""),
            "domain": tsk.get("domain") or inp.get("domain", ""),
            "code_first": {
                "route": cf.get("route"),
                "relevance": cf.get("relevance"),
                "entity_ids": cf.get("entity_ids", []),
                "industries": cf.get("industries", []),
            },
        })

    return {
        "packet_version": "1.0",
        "layer": "L1_ENTITY_RECOGNITION",
        "task": "recognize_and_audit",
        "batch_id": batch_id,
        "task_count": len(batch_tasks),
        "tasks": batch_tasks,
        "entity_catalog_ref": {
            "entities": "data/entities/entities.json",
            "taxonomy": "data/entities/taxonomy.json",
        },
        "output_contract": {
            "schema_name": L1_OUTPUT_SCHEMA,
            "schema_path": f"schemas/{L1_OUTPUT_SCHEMA}.schema.json",
            "format": "JSON array of l1-entity-output-v1 objects or {batch_id, outputs: [...]}",
            "required_fields_per_item": _L1_OUTPUT_REQUIRED,
        },
        "constraints": {
            "surface_must_be_substring_of": "tasks[i].title",
            "citation_must_be_substring_of": "tasks[i].title",
            "recognized_true_requires": ["entities>=1", "citations>=1"],
            "processing_metadata_required": ["agent_provider", "model_used", "timestamp"],
            "audit_duty": "xác nhận entity code-first, sửa nếu sai, bổ sung nếu thiếu",
        },
        "instructions_ref": "schemas/l1-entity-instructions-v1.md",
    }


def write_batch_packet(batch_packet: dict, base_dir: str = "data/agent_tasks") -> str:
    """Ghi gói tác vụ gom lô ra đĩa theo cơ chế hoán đổi nguyên tử an toàn.

    Args:
        batch_packet: Dữ liệu gói tác vụ gom lô.
        base_dir: Thư mục lưu trữ các tệp gói tác vụ.

    Returns:
        Đường dẫn chuỗi tới tệp tin gói tác vụ đã ghi.
    """
    os.makedirs(base_dir, exist_ok=True)
    batch_id = batch_packet.get("batch_id", "batch_01")
    target_path = os.path.join(base_dir, f"{batch_id}.task.json")
    final_path, _ = safe_json_dump(batch_packet, target_path, indent=2)
    return str(final_path)


def split_tasks_into_batches(
    tasks: list[dict],
    batch_size: int = 10,
    base_dir: str = "data/agent_tasks",
    prefix: str = "batch",
    builder=None,
) -> list[str]:
    """Chia danh sách tác vụ thành các lô nhỏ và ghi ra các tệp gói tác vụ tương ứng.

    Args:
        tasks: Danh sách các tác vụ cần phân lô.
        batch_size: Số lượng tác vụ trong mỗi lô.
        base_dir: Thư mục lưu trữ kết quả.
        prefix: Tiền tố đặt tên tệp lô (ví dụ: 'batch', 'l1_batch').
        builder: Hàm đóng gói cấu trúc lô (mặc định là build_batch_packet).

    Returns:
        Danh sách đường dẫn các tệp gói tác vụ lô đã tạo.
    """
    out_paths: list[str] = []
    if not tasks:
        return out_paths

    builder = builder or build_batch_packet
    total = len(tasks)
    batch_idx = 1
    for i in range(0, total, batch_size):
        chunk = tasks[i : i + batch_size]
        batch_id = f"{prefix}_{batch_idx:02d}"
        packet = builder(chunk, batch_id=batch_id)
        path = write_batch_packet(packet, base_dir=base_dir)
        out_paths.append(path)
        batch_idx += 1

    return out_paths


def split_l1_tasks_into_batches(
    tasks: list[dict],
    batch_size: int = 25,
    base_dir: str = "data/agent_tasks/l1",
    prefix: str = "l1_batch",
) -> list[str]:
    """Gom lô cho lớp L1 (packet chỉ có tiêu đề nên lô lớn hơn Gold được)."""
    return split_tasks_into_batches(tasks, batch_size=batch_size, base_dir=base_dir,
                                    prefix=prefix, builder=build_l1_batch_packet)


def unpack_batch_output(batch_output: dict | list | str | Path) -> list[dict]:
    """
    Giải nén output gom lô của Subagent thành danh sách các record agent-output-v1 đơn lẻ.

    Hỗ trợ 3 format phổ biến:
    1. List các objects: [ {"article_id": "..."}, ... ]
    2. Dict có key 'outputs' hoặc 'results': { "batch_id": "...", "outputs": [ ... ] }
    3. Dict đơn lẻ (nếu agent trả 1 bài): { "article_id": "..." }
    """
    data: Any = batch_output
    if isinstance(data, (str, Path)):
        p = Path(data)
        if not p.exists():
            return []
        data = json.loads(p.read_text(encoding="utf-8"))

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict) and "article_id" in item]

    if isinstance(data, dict):
        if "outputs" in data and isinstance(data["outputs"], list):
            return [item for item in data["outputs"] if isinstance(item, dict) and "article_id" in item]
        if "results" in data and isinstance(data["results"], list):
            return [item for item in data["results"] if isinstance(item, dict) and "article_id" in item]
        if "article_id" in data:
            return [data]

    return []
