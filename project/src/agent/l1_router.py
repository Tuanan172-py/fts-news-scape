"""
l1_router.py — QUY TRÌNH 2 TẦNG của lớp L1 nhận diện thực thể theo tiêu đề.

  Tầng 1 — CODE-FIRST (deterministic, l1_classifier): khớp mã + alias.
     → khớp được ≥1 entity ⇒ 'resolved' (tag thẳng, KHÔNG cần agent).
  Tầng 2 — HANDOFF cho AGENT L1: tiêu đề code không khớp (needs_agent)
     → build task-packet self-describing (title + trỏ danh sách + output contract + checklist).

Sau khi agent nộp output → check_l1_dod() gác (schema + grounding + checklist).
Không gọi LLM ở đây. Mirror hạ tầng handoff sẵn có (packet.py / dod.py).
"""
from __future__ import annotations

import json
import os

from src.agent.entities import EntityRegistry, load_registry
from src.agent.l1_classifier import classify_article, title_of
from src.handoff.contract_validator import validate as schema_validate

L1_TASK_VERSION = "1.0"
L1_OUTPUT_SCHEMA = "l1-entity-output-v1"
_CONFIDENCE_MIN = 0.60
_CATEGORY_KEYS = ("ticker_company", "etf_fund", "index", "exchange", "industry_sector")


# ---------------------------------------------------------------------------
# Tầng 1 + định tuyến
# ---------------------------------------------------------------------------
def route_article(article: dict, reg: EntityRegistry | None = None) -> dict:
    """Chạy code-first; trả record kèm `route` ∈ {'resolved','needs_agent'}."""
    reg = reg or load_registry()
    rec = classify_article(article, reg)
    rec["route"] = "needs_agent" if rec["needs_agent"] else "resolved"
    return rec


# ---------------------------------------------------------------------------
# Tầng 2 — task-packet handoff (self-describing, agent-agnostic)
# ---------------------------------------------------------------------------
def build_l1_task_packet(article: dict, code_first: dict) -> dict:
    """Gói 1 tiêu đề cho agent nhận diện + TRA SOÁT. Nhúng kết quả code-first để agent
    xác nhận/sửa/bổ sung (agent có quyền tra soát ngay cả khi code đã khớp)."""
    return {
        "packet_version": L1_TASK_VERSION,
        "layer": "L1_ENTITY_RECOGNITION",
        "task": "recognize_and_audit",
        "article_id": article.get("article_id"),
        "domain": article.get("domain"),
        "input": {
            "title": title_of(article),
            "entity_catalog_ref": {
                "entities": "data/entities/entities.json",
                "taxonomy": "data/entities/taxonomy.json",
            },
            # kết quả code-first để TRA SOÁT: xác nhận / sửa / bổ sung entity bị bỏ sót
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
            "confidence_min": _CONFIDENCE_MIN,
            "surface_must_be_substring_of": "input.title",
            "citation_must_be_substring_of": "input.title",
            "recognized_true_requires": ["entities>=1", "citations>=1"],
            "audit_duty": "xác nhận entity code-first, sửa nếu sai, bổ sung nếu thiếu",
        },
        "instructions_ref": "schemas/l1-entity-instructions-v1.md",
    }


def write_l1_packet(packet: dict, base_dir: str = "data/agent_tasks/l1") -> str:
    os.makedirs(base_dir, exist_ok=True)
    path = os.path.join(base_dir, f"{packet['article_id']}.task.json")
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(packet, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------------------
# DoD — gác output agent L1 (checklist machine-checkable)
# ---------------------------------------------------------------------------
def check_l1_dod(output: dict, title: str) -> tuple[bool, list[str]]:
    """(ok, reasons). ok=True ⇔ tất cả predicate đạt."""
    reasons: list[str] = []

    ok, errs = schema_validate(output, L1_OUTPUT_SCHEMA)
    if not ok:
        reasons.append(f"schema_invalid: {errs[:2]}")
        return False, reasons  # sai schema thì các check sau vô nghĩa

    recognized = output.get("recognized")
    ents = output.get("entities") or []
    cites = output.get("citations") or []

    # grounding: surface & citation ⊂ title
    for i, e in enumerate(ents):
        s = (e or {}).get("surface", "")
        if not s or s not in title:
            reasons.append(f"entities[{i}].surface không phải chuỗi con của title")
    for i, c in enumerate(cites):
        span = (c or {}).get("source_span", "")
        if not span or span not in title:
            reasons.append(f"citations[{i}].source_span không phải chuỗi con của title")

    # nhất quán recognized <-> entities/citations
    if recognized and (len(ents) < 1 or len(cites) < 1):
        reasons.append("recognized=true nhưng thiếu entities/citations")
    if not recognized:
        if ents:
            reasons.append("recognized=false nhưng entities không rỗng")
        cats = output.get("categories") or {}
        if any(cats.get(k) == "done" for k in _CATEGORY_KEYS):
            reasons.append("recognized=false nhưng có category='done'")

    # category 'done' phải có entity in_list thuộc nhóm đó
    cats = output.get("categories") or {}
    type_group = {
        "TICKER": "ticker_company", "SECURITY_OTHER": "ticker_company",
        "ETF": "etf_fund", "INDEX": "index", "EXCHANGE": "exchange",
        "INDUSTRY_GICS1": "industry_sector", "INDUSTRY_GICS2": "industry_sector",
        "INDUSTRY_GICS3": "industry_sector",
    }
    done_groups = {g for g, v in cats.items() if v == "done"}
    have_groups = {type_group.get(e.get("type")) for e in ents if e.get("in_list")}
    for g in done_groups - have_groups:
        reasons.append(f"categories.{g}='done' nhưng không có entity in_list thuộc nhóm")

    conf = output.get("confidence")
    if not isinstance(conf, (int, float)) or conf < _CONFIDENCE_MIN:
        reasons.append(f"confidence {conf} < {_CONFIDENCE_MIN}")

    pm = output.get("processing_metadata") or {}
    for k in ("agent_provider", "model_used", "timestamp"):
        if not pm.get(k):
            reasons.append(f"processing_metadata.{k} missing")

    return (not reasons), reasons
