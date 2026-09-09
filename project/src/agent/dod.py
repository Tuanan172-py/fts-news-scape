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

# Câu "hàm ý" rỗng nghĩa đã đo được trong `agent_outputs` (2026-09-08): 3 template phủ
# 1.274/1.274 bản ghi. Dùng dạng ĐÃ chuẩn hoá (thường + gộp khoảng trắng) để so khớp.
# Mở rộng danh sách qua task-lifecycle-v1.yaml §thresholds.boilerplate_implications,
# KHÔNG cần sửa code.
_DEFAULT_BOILERPLATE = (
    "nội dung bài viết phản ánh thông tin và diễn biến quan trọng",
    "thông tin phản ánh diễn biến hoạt động kinh doanh, cơ cấu tài chính",
    "nội dung bài viết tác động tới nhận định thị trường",
)

# Fallback khớp task-lifecycle-v1.yaml §thresholds (nếu không đọc được YAML).
_DEFAULT_THRESHOLDS = {
    "min_citations": 2,
    "quality_ok": ("high", "medium"),
    "min_implication_len": 40,
    "boilerplate_implications": _DEFAULT_BOILERPLATE,
}
_HELD_STATES = {"SELECTOR_BROKEN", "TEMPLATE_DRIFT"}
# Fix D: span quá ngắn (vd "." / "VN") là chuỗi con của gần như mọi bài → groundedness giả.
_MIN_SPAN_LEN = 20


def _norm(s: str) -> str:
    """Chuẩn hoá để so khớp nguyên văn: gộp khoảng trắng + thường hoá.

    Cần vì kẻ copy hay nối câu bằng ' ' trong khi bản gốc ngăn bằng '\\n' — so thô sẽ trượt.
    """
    return " ".join((s or "").split()).lower()


def load_thresholds() -> dict:
    """Đọc ngưỡng từ task-lifecycle-v1.yaml; thiếu PyYAML/file → default."""
    t = dict(_DEFAULT_THRESHOLDS)
    try:
        import yaml  # optional
        doc = yaml.safe_load((_SCHEMAS_DIR / "task-lifecycle-v1.yaml").read_text("utf-8"))
        th = (doc or {}).get("thresholds", {})
        if "min_citations" in th:
            t["min_citations"] = int(th["min_citations"])
        if "min_implication_len" in th:
            t["min_implication_len"] = int(th["min_implication_len"])
        if th.get("boilerplate_implications"):
            t["boilerplate_implications"] = tuple(
                _norm(x) for x in th["boilerplate_implications"])
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
    """Definition-of-Done. Trả (ok, reasons). ok=True ⇔ TẤT CẢ 6 predicate đạt.

    1 schema_valid | 2 grounded | 3 quality_ok | 4 auditable | 5 value_added | 6 implication_specific.
    (confidence do agent tự khai, calibration kém → KHÔNG dùng làm gate.)

    **Vì sao có predicate 5-6 (thêm 2026-09-08).** Bốn predicate đầu đo được *tính có căn cứ*
    nhưng KHÔNG đo được *có phân tích hay không* — và với kẻ chỉ copy nguyên văn thì phép thử
    groundedness trở nên hiển nhiên đúng. Hệ quả đo trên DB thật: 1.274/1.274 bản ghi
    `agent_outputs` đạt `dod_pass=1`, trong đó 1.274/1.274 có `key_points` copy y hệt
    `citations[].source_span` và 100% `implication.text` là 1 trong 3 câu template. Một cổng
    chưa từng từ chối bản ghi nào thì không phải là cổng.

    Đây vẫn là **validation tất định**, KHÔNG phải giả lập trí tuệ agent (AGENTS.md §6.C):
    nó chỉ TỪ CHỐI output vô giá trị, không tự sinh nội dung thay agent.
    """
    t = thresholds or load_thresholds()
    reasons: list[str] = []

    # 1) schema_valid (hard)
    ok, errs = schema_validate(agent_output, "agent-output-v1")
    if not ok:
        reasons.append(f"schema_invalid: {errs[:2]}")

    # 2) grounded — ≥ min_citations, mỗi source_span ⊂ cleaned_text
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

    # 3) quality_ok (extraction_quality ∈ {high, medium})
    q = agent_output.get("extraction_quality")
    if q not in t["quality_ok"]:
        reasons.append(f"extraction_quality={q!r} not in {t['quality_ok']}")

    # 4) auditable — processing_metadata đủ provider/model/timestamp
    pm = agent_output.get("processing_metadata") or {}
    for k in ("agent_provider", "model_used", "timestamp"):
        if not pm.get(k):
            reasons.append(f"processing_metadata.{k} missing")

    n_clean = _norm(cleaned)
    summ = agent_output.get("summary") or {}

    # 5) value_added — tóm tắt phải là văn bản MỚI, điểm chính phải khác trích dẫn.
    n_abs = _norm(summ.get("abstractive") or "")
    if n_abs and n_clean and n_abs in n_clean:
        reasons.append("summary.abstractive là trích nguyên văn cleaned_text, không phải tóm tắt")
    spans = {_norm((c or {}).get("source_span", "")) for c in cites}
    spans.discard("")
    for i, kp in enumerate(summ.get("key_points") or []):
        if _norm(kp) in spans:
            reasons.append(f"key_points[{i}] copy nguyên văn citations[].source_span")
            break

    # 6) implication_specific — "so-what" phải là nhận định riêng, không phải câu mẫu.
    impl_text = (agent_output.get("implication") or {}).get("text") or ""
    n_impl = _norm(impl_text)
    min_len = t["min_implication_len"]
    if len(impl_text.strip()) < min_len:
        reasons.append(f"implication.text < {min_len} ký tự (quá sơ sài)")
    elif n_impl and n_clean and n_impl in n_clean:
        reasons.append("implication.text là trích nguyên văn cleaned_text, không phải hàm ý")
    elif any(b and b in n_impl for b in t["boilerplate_implications"]):
        reasons.append("implication.text là câu template rỗng nghĩa (boilerplate)")

    return (not reasons), reasons
