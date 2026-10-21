"""Pack articles into mini-batch task packets for agents and unpack the returned outputs."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from src.agent.dod import load_thresholds
from src.core import paths
from src.core.models import VN_TZ
from src.core.staging import safe_json_dump

OUTPUT_SCHEMA = "agent-output-v2-lean"
_OUTPUT_REQUIRED = [
    "article_id", "summary", "key_points", "implication",
    "sentiment", "time_sensitivity", "citations",
]


def build_batch_packet(tasks: list[dict], batch_id: str) -> dict:
    """Pack single task packets into one Gold-layer batch packet.

    Args:
        tasks: Single task packets to group.
        batch_id: Identifier of the batch (for example 'batch_01').

    Returns:
        Self-describing batch packet dict.
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
        "packet_version": "2.0",
        "batch_id": batch_id,
        "task_count": len(batch_tasks),
        "tasks": batch_tasks,
        "output_contract": {
            "schema_name": OUTPUT_SCHEMA,
            "format": "JSON array of agent-output-v2-lean objects or {batch_id, outputs: [...]}",
            "required_fields_per_item": _OUTPUT_REQUIRED,
            "thinking_order": ["summary(tóm tắt)", "implication(hàm ý)", "sentiment", "time_sensitivity"],
        },
        "constraints": {
            "min_citations": t["min_citations"],
            "citations_must_be_substring_of": "tasks[i].cleaned_text",
            "min_citation_len": 20,
            "citations_format": "array of verbatim strings (>= 20 chars each)",
            "metadata_note": "Zero-token metadata: system auto-injects provider, model, timestamp at ingest",
        },
        "instructions_ref": "schemas/agent-instructions-v1.md",
    }


L1_OUTPUT_SCHEMA = "l1-entity-output-v1"
_L1_OUTPUT_REQUIRED = [
    "l1_output_version", "article_id", "title", "recognized",
    "entities", "categories", "citations", "processing_metadata",
]


def build_l1_batch_packet(tasks: list[dict], batch_id: str) -> dict:
    """Pack articles into an L1 entity-recognition batch packet.

    Args:
        tasks: Articles whose entity recognition must be audited.
        batch_id: Identifier of the L1 batch.

    Returns:
        L1 batch packet dict with the code-first hints.
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
            "entities": "entities/entities.json",
            "taxonomy": "entities/taxonomy.json",
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


def write_batch_packet(batch_packet: dict, base_dir: str | Path | None = None) -> str:
    """Write a batch packet to disk through an atomic swap.

    Args:
        batch_packet: Batch packet data.
        base_dir: Directory that receives the packet files.

    Returns:
        Path string of the written packet file.
    """
    base_dir = paths.resolve_data_path(base_dir) if base_dir else paths.agent_tasks_dir()
    os.makedirs(base_dir, exist_ok=True)
    batch_id = batch_packet.get("batch_id", "batch_01")
    target_path = os.path.join(base_dir, f"{batch_id}.task.json")
    final_path, _ = safe_json_dump(batch_packet, target_path, indent=2)
    return str(final_path)


def split_tasks_into_batches(
    tasks: list[dict],
    batch_size: int = 10,
    base_dir: str | Path | None = None,
    prefix: str = "batch",
    builder=None,
) -> list[str]:
    """Split tasks into small batches and write one packet file per batch.

    Args:
        tasks: Tasks to split.
        batch_size: Number of tasks per batch.
        base_dir: Directory that receives the output files.
        prefix: Batch file name prefix (for example 'batch', 'l1_batch').
        builder: Function that builds the batch packet; defaults to build_batch_packet.

    Returns:
        Paths of the batch packet files created.
    """
    out_paths: list[str] = []
    if not tasks:
        return out_paths

    builder = builder or build_batch_packet
    total = len(tasks)
    batch_idx = 1
    # Run tag keeps batch ids unique across runs: a repeated id lets AutoPilot see an
    # existing output file of the same name, skip the new batch and re-ingest stale data
    # (ADR 0008 §1.3). A second-resolution timestamp alone still collides within one
    # second, so 4 random hex characters are appended.
    run_tag = (f"{datetime.now(VN_TZ):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:4]}")
    for i in range(0, total, batch_size):
        chunk = tasks[i : i + batch_size]
        batch_id = f"{prefix}_{run_tag}_{batch_idx:02d}"
        packet = builder(chunk, batch_id=batch_id)
        path = write_batch_packet(packet, base_dir=base_dir)
        out_paths.append(path)
        batch_idx += 1

    return out_paths


def split_l1_tasks_into_batches(
    tasks: list[dict],
    batch_size: int = 25,
    base_dir: str | Path | None = None,
    prefix: str = "l1_batch",
) -> list[str]:
    """Split L1 tasks into batches; L1 packets carry titles only, so batches can be larger than Gold.

    Args:
        tasks: L1 tasks to split.
        batch_size: Number of tasks per batch.
        base_dir: Directory that receives the output files; defaults to the `l1` agent tasks directory.
        prefix: Batch file name prefix.

    Returns:
        Paths of the batch packet files created.
    """
    return split_tasks_into_batches(tasks, batch_size=batch_size,
                                    base_dir=base_dir or paths.agent_tasks_dir() / "l1",
                                    prefix=prefix, builder=build_l1_batch_packet)


def unpack_batch_output(batch_output: dict | list | str | Path) -> list[dict]:
    """Unpack a subagent batch output into single agent-output records.

    Supported formats:
    1. List of objects: [ {"article_id": "..."}, ... ]
    2. Dict with key 'outputs' or 'results': { "batch_id": "...", "outputs": [ ... ] }
    3. Single dict when the agent returns one article: { "article_id": "..." }

    Args:
        batch_output: Parsed output, or path to a JSON file that holds it.

    Returns:
        Records that carry an `article_id`; empty when the path does not exist or the format is unknown.
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
