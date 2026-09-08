"""
batch_handoff.py — Đóng gói và giải nén task gom lô (Consolidated Mini-Batch Handoff).

Mục tiêu:
1. Gom 5–10 bài viết thành 1 file batch task duy nhất (data/agent_tasks/batch_XX.task.json).
2. Giảm 80–90% số lượng Tool Calls (1 lần view_file đọc cả lô, 1 lần write_to_file trả về cả lô).
3. Hỗ trợ giải nén linh hoạt file batch output (mảng JSON hoặc object có key outputs/results).
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
    """Gom danh sách task packets thành 1 batch packet siêu nhẹ tự mô tả."""
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


def write_batch_packet(batch_packet: dict, base_dir: str = "data/agent_tasks") -> str:
    """Ghi batch packet ra đĩa an toàn qua staging (atomic). Trả path."""
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
) -> list[str]:
    """Chia danh sách task thành các mini-batches và ghi ra đĩa. Trả danh sách paths."""
    out_paths: list[str] = []
    if not tasks:
        return out_paths

    total = len(tasks)
    batch_idx = 1
    for i in range(0, total, batch_size):
        chunk = tasks[i : i + batch_size]
        batch_id = f"{prefix}_{batch_idx:02d}"
        packet = build_batch_packet(chunk, batch_id=batch_id)
        path = write_batch_packet(packet, base_dir=base_dir)
        out_paths.append(path)
        batch_idx += 1

    return out_paths


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
