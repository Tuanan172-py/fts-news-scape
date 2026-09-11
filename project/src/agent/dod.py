"""Tiêu chuẩn hoàn thành (Definition-of-Done) và kiểm tra điều kiện tiên quyết cho Agent.

Cung cấp các hàm kiểm tra tính hợp lệ về cấu trúc, độ xác thực căn cứ (groundedness),
tính phân tích gia tăng giá trị (value added) và loại bỏ câu sáo rỗng (boilerplate).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

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
    """Chuẩn hóa chuỗi văn bản bằng cách gộp khoảng trắng và chuyển thành chữ thường."""
    return " ".join((s or "").split()).lower()


def load_thresholds() -> dict:
    """Tải cấu hình các ngưỡng kiểm định chất lượng từ tệp task-lifecycle-v1.yaml.

    Returns:
        Từ điển chứa các ngưỡng kiểm định (min_citations, min_implication_len, ...).
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
    """Kiểm tra các điều kiện tiên quyết của gói công việc trước khi bàn giao cho Agent.

    Args:
        work_package: Dữ liệu gói công việc cần bàn giao.
        check_integrity: Cờ kiểm tra tính toàn vẹn mã băm SHA-256 tệp thô.

    Returns:
        Tuple gồm cờ thành công (True/False) và danh sách chuỗi lý do từ chối nếu có.
    """
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
    """Kiểm định kết quả xử lý của Agent theo bộ 6 tiêu chí hoàn thành Definition-of-Done.

    Bao gồm:
    1. Lược đồ hợp lệ (schema_valid)
    2. Độ xác thực căn cứ trích dẫn trong văn bản (grounded)
    3. Chất lượng trích xuất đạt yêu cầu (quality_ok)
    4. Đầy đủ siêu dữ liệu kiểm toán (auditable)
    5. Có giá trị phân tích mới, không chép nguyên văn (value_added)
    6. Hàm ý sâu sắc, không dùng câu mẫu sáo rỗng (implication_specific)

    Args:
        agent_output: Dữ liệu kết quả do Agent nộp lại.
        work_package: Gói công việc gốc đã giao.
        thresholds: Cấu hình các ngưỡng kiểm định (tùy chọn).

    Returns:
        Tuple gồm cờ đạt chuẩn (True/False) và danh sách các vi phạm nếu có.
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
