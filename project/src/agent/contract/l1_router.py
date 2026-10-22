"""Validate L1 entity recognition records against the l1-entity-output-v1 contract."""
from __future__ import annotations

from src.agent.catalog.entities import load_registry
from src.handoff.contract_validator import validate as schema_validate

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
# Provenance markers of deterministic (code-first) records
# ---------------------------------------------------------------------------
CODE_FIRST_PROVIDER = "code_first"


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

