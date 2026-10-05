"""Bộ phát hiện thay đổi nội dung và cấu trúc DOM của bài viết (Change Detection).

Cung cấp các thuật toán sinh dấu vân tay (SimHash64, DOM path signature)
và phân loại trạng thái bài viết (NEW, UNCHANGED, CONTENT_CHANGED, TEMPLATE_DRIFT, SELECTOR_BROKEN).
"""

from __future__ import annotations

import hashlib
import re

_MASK64 = (1 << 64) - 1
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _token_hash64(token: str) -> int:
    """Băm một token từ khóa thành số nguyên 64-bit bằng Blake2b."""
    return int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(),
                          "big")


def simhash64(text: str) -> int:
    """Tính toán chữ ký SimHash 64-bit của đoạn văn bản.

    Args:
        text: Nội dung văn bản cần tính toán băm tương đồng.

    Returns:
        Số nguyên 64-bit đại diện cho dấu vân tay nội dung (0 nếu văn bản rỗng).
    """
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
    """Tính khoảng cách Hamming (số bit khác biệt) giữa hai chữ ký 64-bit.

    Args:
        a: Số nguyên 64-bit thứ nhất.
        b: Số nguyên 64-bit thứ hai.

    Returns:
        Số lượng bit khác biệt giữa a và b.
    """
    return bin((a ^ b) & _MASK64).count("1")


def dom_path_sig(structure: dict) -> str:
    """Tạo chữ ký cấu trúc DOM không phụ thuộc thứ tự từ siêu dữ liệu cấu trúc Silver.

    Args:
        structure: Từ điển chứa các thành phần cấu trúc (headings, paragraphs, tables, links).

    Returns:
        Chuỗi băm SHA-1 độ dài 12 ký tự biểu diễn cấu trúc DOM, hoặc rỗng nếu không có cấu trúc.
    """
    if not structure:
        return ""
    headings = structure.get("headings", [])
    paragraphs = structure.get("paragraphs", [])
    tables = structure.get("tables", [])
    links = structure.get("links", [])
    if not headings and not paragraphs and not tables:
        return ""
    heads = sorted(f"h{h.get('level')}" for h in headings)

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
    """Tổng hợp bộ dấu vân tay nội dung và trạng thái selector cho một bản capture.

    Args:
        cleaned_text: Văn bản sạch sau khi trích xuất.
        structure: Cấu trúc thành phần DOM của bài viết.
        content_sha256: Mã băm SHA-256 nội dung thô tầng Bronze.
        capture_status: Trạng thái thu thập ('ok', 'partial', 'failed').
        missing: Danh sách các thành phần bị thiếu trong capture.

    Returns:
        Từ điển chứa các chỉ số dấu vân tay và cờ kiểm tra selector.
    """
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
    """Phân loại trạng thái thay đổi bằng cách so sánh hai dấu vân tay kế tiếp.

    Args:
        prev: Dấu vân tay của phiên bản trước đó (hoặc None nếu là bài mới).
        cur: Dấu vân tay của phiên bản hiện tại.
        t_content: Ngưỡng khoảng cách nội dung (tham số dự phòng).
        t_template: Ngưỡng khoảng cách cấu trúc giao diện (tham số dự phòng).

    Returns:
        Tuple gồm mã trạng thái ('NEW', 'UNCHANGED', 'CONTENT_CHANGED',
        'TEMPLATE_DRIFT', 'SELECTOR_BROKEN') và hành động khuyến nghị ('skip', 're_extract', 'manual_review').
    """
    if not cur.get("selector_ok", True):
        return "SELECTOR_BROKEN", "manual_review"

    if prev is None:
        return "NEW", "re_extract"

    if prev.get("content_sha256") and prev["content_sha256"] == cur["content_sha256"]:
        return "UNCHANGED", "skip"

    dom_changed = bool(prev.get("dom_path_sig")) and bool(cur.get("dom_path_sig")) \
        and prev["dom_path_sig"] != cur["dom_path_sig"]
    if dom_changed:
        return "TEMPLATE_DRIFT", "manual_review"
    return "CONTENT_CHANGED", "re_extract"
