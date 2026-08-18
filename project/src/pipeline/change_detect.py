"""
Change-detection — fingerprint + classify để log khi HTML/template đổi (phase-02).

- `content_sha256` (đã có ở Bronze) = exact change, quá nhạy (ad/whitespace flip).
- `simhash64` = fuzzy near-dup của cleaned_text (phân biệt sửa nội dung nhỏ vs khác hẳn).
- `dom_path_sig` = chữ ký cấu trúc DOM (multiset tag-path, order-insensitive) → bắt template drift.
States: NEW | UNCHANGED | CONTENT_CHANGED | TEMPLATE_DRIFT | SELECTOR_BROKEN.
Thuần, deterministic, không network. Xem docs/design/07 §change-detection.
"""

from __future__ import annotations

import hashlib
import re

_MASK64 = (1 << 64) - 1
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _token_hash64(token: str) -> int:
    return int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(),
                          "big")


def simhash64(text: str) -> int:
    """64-bit SimHash của text (token whitespace, lowercase). 0 nếu rỗng."""
    if not text:
        return 0
    tokens = _TOKEN_RE.findall(text.lower())
    if not tokens:
        return 0
    vote = [0] * 64
    for tok in tokens:
        h = _token_hash64(tok)
        for i in range(64):
            vote[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(64):
        if vote[i] > 0:
            out |= (1 << i)
    return out & _MASK64


def hamming64(a: int, b: int) -> int:
    return bin((a ^ b) & _MASK64).count("1")


def dom_path_sig(structure: dict) -> str:
    """Chữ ký cấu trúc order-insensitive từ Silver.structure.
    Dùng multiset (đếm) heading-levels + số paragraph/table/link buckets → ổn định,
    không nhạy với reorder/ad. Trả hex sha1 (12 ký tự)."""
    if not structure:
        return ""
    headings = structure.get("headings", [])
    paragraphs = structure.get("paragraphs", [])
    tables = structure.get("tables", [])
    links = structure.get("links", [])
    # Fix A: không có nội dung cấu trúc (heading/paragraph/table) ⇒ extraction hụt,
    # KHÔNG phải DOM thật để fingerprint → trả "" (classify sẽ không nhầm TEMPLATE_DRIFT).
    if not headings and not paragraphs and not tables:
        return ""
    heads = sorted(f"h{h.get('level')}" for h in headings)
    # bucket hoá số lượng để không nhạy thay đổi nhỏ (log-scale)
    def bucket(n: int) -> int:
        return n.bit_length()
    parts = [
        "H:" + ",".join(heads),
        f"P:{bucket(len(paragraphs))}",
        f"T:{bucket(len(tables))}",
        f"L:{bucket(len(links))}",
    ]
    joined = "|".join(parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12]


def fingerprint(cleaned_text: str, structure: dict, *,
                content_sha256: str, capture_status: str, missing: list | None) -> dict:
    """Trả các dấu vân tay + tín hiệu selector cho 1 bản capture."""
    missing = missing or []
    selector_ok = capture_status in ("ok", "partial") \
        and "main_content_node" not in missing \
        and "incomplete_render" not in missing
    return {
        "content_sha256": content_sha256,
        "simhash64": format(simhash64(cleaned_text), "016x"),
        "dom_path_sig": dom_path_sig(structure),
        "capture_status": capture_status,
        "selector_ok": selector_ok,
    }


def classify(prev: dict | None, cur: dict, *,
             t_content: int = 6, t_template: int = 12) -> tuple[str, str]:
    """So sánh fingerprint hiện tại vs bản trước → (state, recommendation).

    prev/cur: dict fingerprint. Trả state + khuyến nghị (skip|re_extract|manual_review).
    SELECTOR_BROKEN ưu tiên cao nhất.
    """
    # selector hỏng → luôn cần người xem, dù có prev hay không
    if not cur.get("selector_ok", True):
        return "SELECTOR_BROKEN", "manual_review"

    if prev is None:
        return "NEW", "re_extract"

    if prev.get("content_sha256") and prev["content_sha256"] == cur["content_sha256"]:
        return "UNCHANGED", "skip"

    # TEMPLATE_DRIFT chỉ do CẤU TRÚC DOM đổi — KHÔNG dựa vào độ lớn thay đổi nội dung
    # (thay đổi nội dung lớn nhưng cùng template vẫn là CONTENT_CHANGED). t_content/
    # t_template giữ cho tương thích + log/tuning tương lai, không quyết định template.
    # Fix A: chỉ TEMPLATE_DRIFT khi CẢ HAI sig non-empty & khác nhau. Nếu cur sig rỗng
    # (extraction hụt cấu trúc) → không nhầm drift; rơi về CONTENT_CHANGED (re_extract).
    dom_changed = bool(prev.get("dom_path_sig")) and bool(cur.get("dom_path_sig")) \
        and prev["dom_path_sig"] != cur["dom_path_sig"]
    if dom_changed:
        return "TEMPLATE_DRIFT", "manual_review"
    return "CONTENT_CHANGED", "re_extract"
