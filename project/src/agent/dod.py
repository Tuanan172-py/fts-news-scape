"""Check Definition-of-Done criteria and preconditions for agent outputs."""

from __future__ import annotations

import hashlib
from pathlib import Path

from src.core import paths
from src.handoff.contract_validator import validate as schema_validate

_SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"

_DEFAULT_BOILERPLATE = (
    "nội dung bài viết phản ánh thông tin và diễn biến quan trọng",
    "thông tin phản ánh diễn biến hoạt động kinh doanh, cơ cấu tài chính",
    "nội dung bài viết tác động tới nhận định thị trường",
)

_DEFAULT_THRESHOLDS = {
    "min_citations": 2,
    "quality_ok": ("high", "medium"),
    "min_implication_len": 40,
    "boilerplate_implications": _DEFAULT_BOILERPLATE,
}
_HELD_STATES = {"SELECTOR_BROKEN", "TEMPLATE_DRIFT"}
_MIN_SPAN_LEN = 20


def _norm(s: str) -> str:
    """Normalize text by collapsing whitespace and lowercasing.

    Args:
        s: Text to normalize; None is treated as empty.

    Returns:
        Normalized lowercase string.
    """
    return " ".join((s or "").split()).lower()


def load_thresholds() -> dict:
    """Load the quality thresholds from task-lifecycle-v1.yaml.

    Returns:
        Dict of thresholds (min_citations, min_implication_len, ...); defaults apply when the file is unreadable.
    """
    t = dict(_DEFAULT_THRESHOLDS)
    try:
        import yaml
        doc = yaml.safe_load((_SCHEMAS_DIR / "task-lifecycle-v1.yaml").read_text("utf-8"))
        th = (doc or {}).get("thresholds", {})
        if "min_citations" in th:
            t["min_citations"] = int(th["min_citations"])
        if "min_implication_len" in th:
            t["min_implication_len"] = int(th["min_implication_len"])
        if th.get("boilerplate_implications"):
            t["boilerplate_implications"] = tuple(
                _norm(x) for x in th["boilerplate_implications"])
    except Exception:
        pass
    return t


def verify_preconditions(work_package: dict, *, check_integrity: bool = True) -> tuple[bool, list[str]]:
    """Check the preconditions of a work package before hand-off to an agent.

    Args:
        work_package: Work package to hand off.
        check_integrity: Whether to verify the SHA-256 hash of the raw file.

    Returns:
        Tuple of the success flag and the list of rejection reasons, if any.
    """
    reasons: list[str] = []
    if work_package.get("change_state") in _HELD_STATES:
        reasons.append(f"precondition: change_state={work_package.get('change_state')} → held")
    if check_integrity:
        raw_path = work_package.get("raw_html_path", "")
        want = work_package.get("raw_sha256", "")
        if raw_path:
            p = paths.resolve_data_path(raw_path)
            if not p.is_file():
                reasons.append(f"precondition: raw missing {raw_path}")
            else:
                got = hashlib.sha256(p.read_bytes()).hexdigest()
                if got != want:
                    reasons.append("precondition: raw_sha256 mismatch (integrity)")
    return (not reasons), reasons


def check_dod(agent_output: dict, work_package: dict,
              thresholds: dict | None = None) -> tuple[bool, list[str]]:
    """Validate an agent output against the six Definition-of-Done criteria.

    Criteria:
    1. Valid schema (schema_valid)
    2. Citations grounded in the text (grounded)
    3. Acceptable extraction quality (quality_ok)
    4. Complete audit metadata (auditable)
    5. New analytical content, not a verbatim copy (value_added)
    6. Specific implication, not a template sentence (implication_specific)

    Args:
        agent_output: Result data submitted by the agent.
        work_package: Original work package that was handed off.
        thresholds: Optional validation thresholds; defaults to load_thresholds().

    Returns:
        Tuple of the pass flag and the list of violations, if any.
    """
    t = thresholds or load_thresholds()
    reasons: list[str] = []

    # 1) schema_valid (hard): supports agent-output-v2-lean and agent-output-v1.
    is_lean = (
        isinstance(agent_output.get("summary"), str)
        or isinstance(agent_output.get("implication"), str)
        or (isinstance(agent_output.get("citations"), list) and agent_output.get("citations") and isinstance(agent_output["citations"][0], str))
        or "lean" in str(agent_output.get("output_schema_version", "")).lower()
    )
    schema_name = "agent-output-v2-lean" if is_lean else "agent-output-v1"
    ok, errs = schema_validate(agent_output, schema_name)
    if not ok:
        # Try the other schema when the initial detection was wrong.
        alt_schema = "agent-output-v1" if is_lean else "agent-output-v2-lean"
        ok_alt, _ = schema_validate(agent_output, alt_schema)
        if ok_alt:
            ok = True
            is_lean = (alt_schema == "agent-output-v2-lean")
    if not ok:
        reasons.append(f"schema_invalid: {errs[:2]}")

    # 2) grounded: enough citations per threshold and every source_span is inside cleaned_text.
    # A single-paragraph article marked with `citation_basis` by the expander needs only
    # one citation (ADR 0018); otherwise `min_citations` applies.
    cites = agent_output.get("citations") or []
    cleaned = work_package.get("cleaned_text", "") or ""
    need_cites = (1 if agent_output.get("citation_basis") == "single-paragraph"
                  else t["min_citations"])
    if len(cites) < need_cites:
        reasons.append(f"citations {len(cites)} < {need_cites}")
    for i, c in enumerate(cites):
        if isinstance(c, str):
            span = c
        elif isinstance(c, dict):
            span = c.get("source_span", "")
        else:
            span = ""
        if not span or len(span.strip()) < _MIN_SPAN_LEN:
            reasons.append(f"citation[{i}] source_span too short (<{_MIN_SPAN_LEN} chars)")
        elif span not in cleaned:
            reasons.append(f"citation[{i}] not grounded in cleaned_text")

    # 3) quality_ok (extraction_quality in {high, medium}): checked for schema v1 only.
    if not is_lean:
        q = agent_output.get("extraction_quality")
        if q not in t["quality_ok"]:
            reasons.append(f"extraction_quality={q!r} not in {t['quality_ok']}")

    # 4) auditable: processing_metadata has provider, model and timestamp (v1); the system fills them for v2-lean.
    if not is_lean:
        pm = agent_output.get("processing_metadata") or {}
        for k in ("agent_provider", "model_used", "timestamp"):
            if not pm.get(k):
                reasons.append(f"processing_metadata.{k} missing")

    n_clean = _norm(cleaned)
    summ = agent_output.get("summary")
    if isinstance(summ, str):
        n_abs = _norm(summ)
        key_pts = agent_output.get("key_points") or []
    elif isinstance(summ, dict):
        n_abs = _norm(summ.get("abstractive") or "")
        key_pts = summ.get("key_points") or agent_output.get("key_points") or []
    else:
        n_abs = ""
        key_pts = []

    # 5) value_added: the summary must be new text and key points must differ from the citations.
    if n_abs and n_clean and n_abs in n_clean:
        reasons.append("summary.abstractive là trích nguyên văn cleaned_text, không phải tóm tắt")
    spans = set()
    for c in cites:
        span_str = c if isinstance(c, str) else (c.get("source_span", "") if isinstance(c, dict) else "")
        if span_str:
            spans.add(_norm(span_str))
    spans.discard("")
    for i, kp in enumerate(key_pts):
        if _norm(kp) in spans:
            reasons.append(f"key_points[{i}] copy nguyên văn citations[].source_span")
            break

    # 6) implication_specific: the implication must be an original assessment, not a template sentence.
    impl = agent_output.get("implication")
    if isinstance(impl, str):
        impl_text = impl
    elif isinstance(impl, dict):
        impl_text = impl.get("text") or ""
    else:
        impl_text = ""
    n_impl = _norm(impl_text)
    min_len = t["min_implication_len"]
    if len(impl_text.strip()) < min_len:
        reasons.append(f"implication.text < {min_len} ký tự (quá sơ sài)")
    elif n_impl and n_clean and n_impl in n_clean:
        reasons.append("implication.text là trích nguyên văn cleaned_text, không phải hàm ý")
    elif any(b and b in n_impl for b in t["boilerplate_implications"]):
        reasons.append("implication.text là câu template rỗng nghĩa (boilerplate)")

    return (not reasons), reasons
