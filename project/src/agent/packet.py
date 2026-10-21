"""Build task packets that hand work packages to agents."""

from __future__ import annotations

import json
import os
from pathlib import Path

from src.agent.dod import load_thresholds
from src.core import paths
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
    """Build the cleaned input payload for an agent task.

    Args:
        work_package: Source work-package-v1 package.
        l1_entities: Optional list of recognized L1 entities.
        prune: Whether to strip junk text and boilerplate.

    Returns:
        Compact input data dict.
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
    # structure.headings is excluded on purpose: junk and sidebar headings waste tokens and induce hallucination.

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
    """Build a task packet with the output contract and constraints.

    Args:
        work_package: Source work package that holds the article content.
        work_item_id: Identifier of the task record in the processing queue.
        l1_entities: Tagged L1 entities.
        prune: Whether to strip redundant text.
        schema_name: Name of the output contract schema.

    Returns:
        Complete task packet dict that follows the agent communication contract.
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
        # Input: pruned cleaned_text without boilerplate.
        "input": gold_input,
        # Output contract: the agent must emit exactly this schema.
        "output_contract": {
            "schema_name": schema_name,
            "schema_path": f"schemas/{schema_name}.schema.json",
            "required": required_fields,
            "thinking_order": ["summary(tóm tắt)", "implication(hàm ý)", "sentiment", "time_sensitivity"],
        },
        # Constraints the agent self-checks before submitting (match the DoD at ingest).
        "constraints": constraints,
        "instructions_ref": "schemas/agent-instructions-v1.md",
    }


from src.core.staging import safe_json_dump


def write_packet(packet: dict, base_dir: str | Path | None = None) -> str:
    """Write a task packet to disk through atomic staging.

    Args:
        packet: Packet data to write.
        base_dir: Root directory that stores the packets.

    Returns:
        Path of the packet file written to disk.
    """
    base_dir = paths.resolve_data_path(base_dir) if base_dir else paths.agent_tasks_dir()
    os.makedirs(base_dir, exist_ok=True)
    target_path = os.path.join(base_dir, f"{packet['article_id']}.task.json")
    final_path, _ = safe_json_dump(packet, target_path, indent=2)
    return str(final_path)
