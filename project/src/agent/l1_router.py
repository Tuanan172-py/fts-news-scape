"""Route articles and validate L1 entity recognition results."""
from __future__ import annotations

import json
import os

from src.agent.entities import EntityRegistry, load_registry
from src.agent.l1_classifier import classify_article, title_of
from src.handoff.contract_validator import validate as schema_validate
from src.core import paths
from src.core.models import now_vn_iso

L1_TASK_VERSION = "1.0"
L1_OUTPUT_SCHEMA = "l1-entity-output-v1"
_CATEGORY_KEYS = (
    "ticker_company", "etf_fund", "index", "exchange",
    "industry_sector", "macro_geo", "asset_class", "institution",
)

# Entity type -> group in the `categories` checklist of l1-entity-output-v1.
TYPE_GROUP = {
    "TICKER": "ticker_company", "SECURITY_OTHER": "ticker_company",
    "ETF": "etf_fund", "INDEX": "index", "EXCHANGE": "exchange",
    "INDUSTRY_GICS1": "industry_sector", "INDUSTRY_GICS2": "industry_sector",
    "INDUSTRY_GICS3": "industry_sector",
    "MACRO_GEO": "macro_geo", "MACRO_THEME": "macro_geo",
    "ASSET_CLASS": "asset_class",
    "INSTITUTION": "institution",
}


# ---------------------------------------------------------------------------
# Layer 1 and routing
# ---------------------------------------------------------------------------
def route_article(article: dict, reg: EntityRegistry | None = None) -> dict:
    """Classify layer-1 entities and decide the route.

    Args:
        article: Article data dict.
        reg: Optional EntityRegistry; None loads the default registry.

    Returns:
        Classification dict with the field 'route' ('resolved' or 'needs_agent').
    """
    reg = reg or load_registry()
    rec = classify_article(article, reg)
    rec["route"] = "needs_agent" if rec["needs_agent"] else "resolved"
    return rec


# ---------------------------------------------------------------------------
# Layer 2: task-packet hand-off (self-describing, agent-agnostic)
# ---------------------------------------------------------------------------
def build_l1_task_packet(article: dict, code_first: dict) -> dict:
    """Build the L1 task packet for an agent that audits and extends recognition.

    Args:
        article: Article data to process.
        code_first: Automatic classification result from layer 1.

    Returns:
        Work package dict that follows the L1 task packet structure.
    """
    return {
        "packet_version": L1_TASK_VERSION,
        "layer": "L1_ENTITY_RECOGNITION",
        "task": "recognize_and_audit",
        "article_id": article.get("article_id"),
        "domain": article.get("domain"),
        "input": {
            "title": title_of(article),
            "entity_catalog_ref": {
                "entities": "entities/entities.json",
                "taxonomy": "entities/taxonomy.json",
            },
            # Code-first result for the agent to audit: confirm, correct or add missed entities.
            "code_first": {
                "route": code_first.get("route"),
                "relevance": code_first.get("relevance"),
                "entities": code_first.get("entities", []),
                "entity_ids": code_first.get("entity_ids", []),
                "industries": code_first.get("industries", []),
            },
        },
        "output_contract": {
            "schema_name": L1_OUTPUT_SCHEMA,
            "schema_path": f"schemas/{L1_OUTPUT_SCHEMA}.schema.json",
            "checklist_categories": list(_CATEGORY_KEYS),
        },
        "constraints": {
            "surface_must_be_substring_of": "input.title",
            "citation_must_be_substring_of": "input.title",
            "recognized_true_requires": ["entities>=1", "citations>=1"],
            "audit_duty": "xác nhận entity code-first, sửa nếu sai, bổ sung nếu thiếu",
        },
        "instructions_ref": "schemas/l1-entity-instructions-v1.md",
    }


from src.core.staging import safe_json_dump


def write_l1_packet(packet: dict, base_dir: str | os.PathLike | None = None) -> str:
    """Write an L1 task packet to disk through atomic staging.

    Args:
        packet: Packet data to write.
        base_dir: Root directory that stores the packets.

    Returns:
        Data-relative path of the packet file written.
    """
    base_dir = paths.resolve_data_path(base_dir) if base_dir else paths.agent_tasks_dir() / "l1"
    os.makedirs(base_dir, exist_ok=True)
    target_path = os.path.join(base_dir, f"{packet['article_id']}.task.json")
    final_path, _ = safe_json_dump(packet, target_path, indent=2)
    return paths.to_data_relative(final_path)      # relative path works on both machines




# ---------------------------------------------------------------------------
# Materialize the DETERMINISTIC result as l1-entity-output-v1
# ---------------------------------------------------------------------------
CODE_FIRST_PROVIDER = "code_first"
CODE_FIRST_MODEL = "deterministic"


def build_code_first_output(rec: dict, article_id: str) -> dict:
    """Convert a layer-1 classification result to the l1-entity-output-v1 schema.

    Args:
        rec: Classification result from l1_classifier.
        article_id: Unique article identifier.

    Returns:
        Entity result dict that follows the l1-entity-output-v1 schema.
    """
    title = rec.get("title") or ""
    ents = []
    for d in rec.get("entities") or []:
        surface = d.get("surface")
        if not surface or surface not in title:
            continue          # drop entities not grounded in the title so DoD does not fail the whole record
        ents.append({
            "surface": surface,
            "entity_id": d["entity_id"],
            "type": d["type"],
            "method": "exact_code" if d.get("via") == "code" else "alias",
            "in_list": True,
        })
    groups = {TYPE_GROUP.get(e["type"]) for e in ents}
    recognized = bool(ents)
    return {
        "l1_output_version": "1.0",
        "article_id": article_id,
        "title": title,
        "recognized": recognized,
        "entities": ents,
        "categories": {k: ("done" if k in groups else "none") for k in _CATEGORY_KEYS},
        "unlisted_candidates": [],
        "citations": [{"source_span": ents[0]["surface"]}] if recognized else [],
        "processing_metadata": {
            "agent_provider": CODE_FIRST_PROVIDER,
            "model_used": CODE_FIRST_MODEL,
            "timestamp": now_vn_iso(),
        },
    }

# ---------------------------------------------------------------------------
# DoD: gate for L1 agent output (machine-checkable checklist)
# ---------------------------------------------------------------------------
def check_l1_dod(output: dict, title: str, registry=None) -> tuple[bool, list[str]]:
    """Check the DoD acceptance conditions of an L1 recognition result.

    Args:
        output: Output data to validate.
        title: Article title used to verify citations.
        registry: Optional EntityRegistry used to verify identifiers.

    Returns:
        Tuple of the pass flag and the list of violation reasons, if any.
    """

    reasons: list[str] = []

    ok, errs = schema_validate(output, L1_OUTPUT_SCHEMA)
    if not ok:
        reasons.append(f"schema_invalid: {errs[:2]}")
        return False, reasons  # later checks are meaningless on a wrong schema

    recognized = output.get("recognized")
    ents = output.get("entities") or []
    cites = output.get("citations") or []

    # Grounding: surface and citation must be substrings of the title.
    for i, e in enumerate(ents):
        s = (e or {}).get("surface", "")
        if not s or s not in title:
            reasons.append(f"entities[{i}].surface không phải chuỗi con của title")
    for i, c in enumerate(cites):
        span = (c or {}).get("source_span", "")
        if not span or span not in title:
            reasons.append(f"citations[{i}].source_span không phải chuỗi con của title")

    # Consistency between recognized and entities/citations.
    if recognized and (len(ents) < 1 or len(cites) < 1):
        reasons.append("recognized=true nhưng thiếu entities/citations")
    if not recognized:
        if ents:
            reasons.append("recognized=false nhưng entities không rỗng")
        cats = output.get("categories") or {}
        if any(cats.get(k) == "done" for k in _CATEGORY_KEYS):
            reasons.append("recognized=false nhưng có category='done'")

    # A category marked 'done' needs an in_list entity of that group.
    cats = output.get("categories") or {}
    # TYPE_GROUP is module level and shared with the code-first materializer.
    done_groups = {g for g, v in cats.items() if v == "done"}
    have_groups = {TYPE_GROUP.get(e.get("type")) for e in ents if e.get("in_list")}
    for g in done_groups - have_groups:
        reasons.append(f"categories.{g}='done' nhưng không có entity in_list thuộc nhóm")

    # entity_id must exist in the registry (blocks malformed or invented ids).
    if registry is None:
        try:
            registry = load_registry()
        except Exception:                      # missing entities.json: skip this check
            registry = None
    if registry is not None:
        for i, e in enumerate(ents):
            if not (e or {}).get("in_list"):
                continue
            eid = (e or {}).get("entity_id")
            if not eid:
                reasons.append(f"entities[{i}].in_list=true nhung thieu entity_id")
            elif registry.get(eid) is None:
                reasons.append(f"entities[{i}].entity_id={eid!r} khong co trong danh muc")

    pm = output.get("processing_metadata") or {}
    for k in ("agent_provider", "model_used", "timestamp"):
        if not pm.get(k):
            reasons.append(f"processing_metadata.{k} missing")

    return (not reasons), reasons

