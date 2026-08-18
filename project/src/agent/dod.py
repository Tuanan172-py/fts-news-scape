"""
Definition-of-Done + preconditions — "điểm chạm báo hiệu công việc ĐÃ THỰC SỰ hoàn thành".

Thuần (pure), machine-checkable, KHÔNG gọi LLM. Hiện thực đúng
schemas/task-lifecycle-v1.yaml §definition_of_done + §preconditions (doc 10 §5-6).
Dùng lại `contract_validator` cho predicate schema_valid (DRY).

Ngưỡng đọc từ task-lifecycle-v1.yaml nếu có (PyYAML), else fallback hằng số khớp spec.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from src.handoff.contract_validator import validate as schema_validate

_SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"

# Fallback khớp task-lifecycle-v1.yaml §thresholds (nếu không đọc được YAML).
_DEFAULT_THRESHOLDS = {
    "confidence_min": 0.65,
    "min_citations": 2,
    "quality_ok": ("high", "medium"),
}
_HELD_STATES = {"SELECTOR_BROKEN", "TEMPLATE_DRIFT"}
# Fix D: span quá ngắn (vd "." / "VN") là chuỗi con của gần như mọi bài → groundedness giả.
_MIN_SPAN_LEN = 20


def load_thresholds() -> dict:
    """Đọc ngưỡng từ task-lifecycle-v1.yaml; thiếu PyYAML/file → default."""
    t = dict(_DEFAULT_THRESHOLDS)
    try:
        import yaml  # optional
        doc = yaml.safe_load((_SCHEMAS_DIR / "task-lifecycle-v1.yaml").read_text("utf-8"))
        th = (doc or {}).get("thresholds", {})
        if "confidence_min" in th:
            t["confidence_min"] = float(th["confidence_min"])
        if "min_citations" in th:
            t["min_citations"] = int(th["min_citations"])
    except Exception:  # noqa: BLE001 — spec fallback là hợp lệ
        pass
    return t


def verify_preconditions(work_package: dict, *, check_integrity: bool = True) -> tuple[bool, list[str]]:
    """Guardrail TRƯỚC khi giao agent (doc 10 §6). (ok, reasons)."""
    reasons: list[str] = []
    if work_package.get("change_state") in _HELD_STATES:
        reasons.append(f"precondition: change_state={work_package.get('change_state')} → held")
    if check_integrity:
        raw_path = work_package.get("raw_html_path", "")
        want = work_package.get("raw_sha256", "")
        p = Path(raw_path)
        if not p.exists():
            reasons.append(f"precondition: raw missing {raw_path}")
        else:
            got = hashlib.sha256(p.read_bytes()).hexdigest()
            if got != want:
                reasons.append("precondition: raw_sha256 mismatch (integrity)")
    return (not reasons), reasons


def check_dod(agent_output: dict, work_package: dict,
              thresholds: dict | None = None) -> tuple[bool, list[str]]:
    """Definition-of-Done. Trả (ok, reasons). ok=True ⇔ TẤT CẢ 5 predicate đạt.

    1 schema_valid | 2 confident | 3 grounded | 4 quality_ok | 5 auditable.
    """
    t = thresholds or load_thresholds()
    reasons: list[str] = []

    # 1) schema_valid (hard)
    ok, errs = schema_validate(agent_output, "agent-output-v1")
    if not ok:
        reasons.append(f"schema_invalid: {errs[:2]}")

    # 2) confident
    conf = agent_output.get("confidence")
    if not isinstance(conf, (int, float)) or conf < t["confidence_min"]:
        reasons.append(f"confidence {conf} < {t['confidence_min']}")

    # 3) grounded — ≥ min_citations, mỗi source_span ⊂ cleaned_text
    cites = agent_output.get("citations") or []
    cleaned = work_package.get("cleaned_text", "") or ""
    if len(cites) < t["min_citations"]:
        reasons.append(f"citations {len(cites)} < {t['min_citations']}")
    for i, c in enumerate(cites):
        span = (c or {}).get("source_span", "")
        if not span or len(span.strip()) < _MIN_SPAN_LEN:
            reasons.append(f"citation[{i}] source_span too short (<{_MIN_SPAN_LEN} chars)")
        elif span not in cleaned:
            reasons.append(f"citation[{i}] not grounded in cleaned_text")

    # 4) quality_ok (extraction_quality ∈ {high, medium})
    q = agent_output.get("extraction_quality")
    if q not in t["quality_ok"]:
        reasons.append(f"extraction_quality={q!r} not in {t['quality_ok']}")

    # 5) auditable — processing_metadata đủ provider/model/timestamp
    pm = agent_output.get("processing_metadata") or {}
    for k in ("agent_provider", "model_used", "timestamp"):
        if not pm.get(k):
            reasons.append(f"processing_metadata.{k} missing")

    return (not reasons), reasons
