"""Định tuyến và kiểm định kết quả nhận diện thực thể tầng L1."""
from __future__ import annotations

import json
import os

from src.agent.entities import EntityRegistry, load_registry
from src.agent.l1_classifier import classify_article, title_of
from src.handoff.contract_validator import validate as schema_validate
from src.core.config import to_project_relative
from src.core.models import now_vn_iso

L1_TASK_VERSION = "1.0"
L1_OUTPUT_SCHEMA = "l1-entity-output-v1"
_CATEGORY_KEYS = (
    "ticker_company", "etf_fund", "index", "exchange",
    "industry_sector", "macro_geo", "asset_class", "institution",
)

# type entity -> nhom trong checklist `categories` cua l1-entity-output-v1.
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
# Tầng 1 + định tuyến
# ---------------------------------------------------------------------------
def route_article(article: dict, reg: EntityRegistry | None = None) -> dict:
    """Phân loại thực thể tầng 1 và xác định hướng định tuyến.

    Args:
        article: Từ điển chứa dữ liệu bài viết.
        reg: Sổ đăng ký thực thể EntityRegistry tùy chọn.

    Returns:
        Từ điển kết quả phân loại kèm trường 'route' ('resolved' hoặc 'needs_agent').
    """
    reg = reg or load_registry()
    rec = classify_article(article, reg)
    rec["route"] = "needs_agent" if rec["needs_agent"] else "resolved"
    return rec


# ---------------------------------------------------------------------------
# Tầng 2 — task-packet handoff (self-describing, agent-agnostic)
# ---------------------------------------------------------------------------
def build_l1_task_packet(article: dict, code_first: dict) -> dict:
    """Đóng gói gói công việc L1 cho agent tra soát và nhận diện bổ sung.

    Args:
        article: Dữ liệu bài viết cần xử lý.
        code_first: Kết quả phân loại tự động từ tầng 1.

    Returns:
        Từ điển gói công việc tuân thủ cấu trúc L1 task packet.
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
            "surface_must_be_substring_of": "input.title",
            "citation_must_be_substring_of": "input.title",
            "recognized_true_requires": ["entities>=1", "citations>=1"],
            "audit_duty": "xác nhận entity code-first, sửa nếu sai, bổ sung nếu thiếu",
        },
        "instructions_ref": "schemas/l1-entity-instructions-v1.md",
    }


from src.core.staging import safe_json_dump


def write_l1_packet(packet: dict, base_dir: str = "data/agent_tasks/l1") -> str:
    """Lưu gói công việc L1 vào đĩa qua cơ chế staging nguyên tử.

    Args:
        packet: Dữ liệu gói công việc cần ghi.
        base_dir: Thư mục gốc lưu trữ gói công việc.

    Returns:
        Đường dẫn tương đối tới tệp task packet đã ghi.
    """
    os.makedirs(base_dir, exist_ok=True)
    target_path = os.path.join(base_dir, f"{packet['article_id']}.task.json")
    final_path, _ = safe_json_dump(packet, target_path, indent=2)
    return to_project_relative(final_path)      # tuong doi -> chay duoc tren ca 2 may




# ---------------------------------------------------------------------------
# Vat chat hoa ket qua TAT DINH thanh l1-entity-output-v1
# ---------------------------------------------------------------------------
CODE_FIRST_PROVIDER = "code_first"
CODE_FIRST_MODEL = "deterministic"


def build_code_first_output(rec: dict, article_id: str) -> dict:
    """Chuyển đổi kết quả phân loại tầng 1 sang schema l1-entity-output-v1.

    Args:
        rec: Kết quả phân loại từ l1_classifier.
        article_id: Định danh duy nhất của bài viết.

    Returns:
        Từ điển kết quả thực thể tuân thủ schema l1-entity-output-v1.
    """
    title = rec.get("title") or ""
    ents = []
    for d in rec.get("entities") or []:
        surface = d.get("surface")
        if not surface or surface not in title:
            continue          # khong ground duoc vao title thi bo, dung de DoD truot ca ban ghi
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
# DoD — gác output agent L1 (checklist machine-checkable)
# ---------------------------------------------------------------------------
def check_l1_dod(output: dict, title: str, registry=None) -> tuple[bool, list[str]]:
    """Kiểm tra điều kiện nghiệm thu DoD đối với kết quả nhận diện L1.

    Args:
        output: Dữ liệu kết quả đầu ra cần kiểm định.
        title: Tiêu đề bài viết dùng để đối soát trích dẫn.
        registry: Sổ đăng ký thực thể EntityRegistry tùy chọn để kiểm tra ID.

    Returns:
        Tuple gồm trạng thái đạt chuẩn (True/False) và danh sách lý do vi phạm nếu có.
    """

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
    # type_group -> TYPE_GROUP (module level, dung chung voi bo vat chat hoa code-first)
    done_groups = {g for g, v in cats.items() if v == "done"}
    have_groups = {TYPE_GROUP.get(e.get("type")) for e in ents if e.get("in_list")}
    for g in done_groups - have_groups:
        reasons.append(f"categories.{g}='done' nhưng không có entity in_list thuộc nhóm")

    # entity_id phai co that trong registry (chan id sai dang / bia)
    if registry is None:
        try:
            registry = load_registry()
        except Exception:                      # thieu entities.json -> bo qua check nay
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

