"""
pruner.py — Tinh lọc đoạn văn sạch (Clean Paragraph Pruning) cho Subagents Gold.

Tuân thủ Invariant Rule 05 (Clean Paragraph Payload Invariant):
1. Chỉ giữ lại các đoạn văn cốt lõi của bài báo.
2. Loại bỏ 100% boilerplate: teaser "Bài liên quan", thông tin tòa soạn, hotline, quảng cáo, copyright.
3. BẢO TOÀN NGUYÊN VĂN (Verbatim Span Preservation): Không sửa/cắt ngang trong đoạn văn,
   đảm bảo citations.source_span của Agent luôn là exact substring của cleaned_text.
4. Áp dụng Inverted Pyramid: Giới hạn trần ký tự (mặc định 4.000 chars) bằng cách lấy đủ các
   đoạn văn đầu tiên quan trọng nhất, tránh phình context window.
"""

from __future__ import annotations

import re

# Các mẫu regex phát hiện đoạn văn rác/boilerplate cần loại bỏ
_BOILERPLATE_PATTERNS = [
    # Teaser / Tin liên quan
    r"^(?:bài\s+liên\s+quan|tin\s+cùng\s+chuyên\s+mục|xem\s+thêm\b|đọc\s+tiếp\b|có\s+thể\s+bạn\s+quan\s+tâm|tin\s+khác\b|chuyên\s+mục\s+đặc\s+biệt)",
    # Thông tin liên hệ tòa soạn & quảng cáo
    r"^(?:ban\s+biên\s+tập|tổng\s+biên\s+tập|chịu\s+trách\s+nhiệm\s+nội\s+dung|địa\s+chỉ\s*:\s*tầng|trụ\s+sở\b|tòa\s+nhà\b)",
    r"^(?:liên\s+hệ\s+quảng\s+cáo|liên\s+hệ\s+dữ\s+liệu|báo\s+giá\s+quảng\s+cáo|quảng\s+cáo\s*:\s*)",
    r"^(?:hotline\s*:|email\s*:|điện\s+thoại\s*:|đt\s*:|máy\s+lẻ\b|fax\s*:)",
    r"(?:giấy\s+phép\s+(?:thiết\s+lập|hoạt\s+động|xuất\s+bản)|sở\s+thông\s+tin\s+và\s+truyền\s+thông)",
    r"^(?:©\s*copyright|bản\s+quyền\s+thuộc\s+về|toàn\s+bộ\s+bản\s+quyền)",
    # Điều hướng cỡ chữ / giao diện
    r"^(?:chọn\s+cỡ\s+chữ|chia\s+sẻ\s+bài\s+viết|theo\s+dõi\s+chúng\s+tôi\s+trên|in\s+bài\s+viết)",
    # Rác bảng định dạng thô (ví dụ: '| | |' hoặc chỉ có dấu gạch)
    r"^[\s\|\:\-]+$",
]

_COMPILED_BOILERPLATE = [re.compile(p, re.IGNORECASE) for p in _BOILERPLATE_PATTERNS]

# Bút danh / nguồn tin đơn độc ngắn < 40 ký tự ở cuối bài
_FOOTER_SOURCE_PATTERN = re.compile(
    r"^(?:theo\s+(?:hose|hnx|upcom|cafef|vietstock|vneconomy|ttxvn|reuters|bloomberg|dân\s+trí|đầu\s+tư|tiền\s+phong)|nguồn\s*:)\b.*$",
    re.IGNORECASE,
)


def is_boilerplate_paragraph(para: str) -> bool:
    """Kiểm tra một đoạn văn có phải là rác thông tin / boilerplate không."""
    stripped = para.strip()
    if not stripped:
        return True

    # Đoạn văn quá ngắn dạng ký tự đặc biệt hoặc gạch nối
    if len(stripped) <= 3 and not stripped.isalnum():
        return True

    # Khớp các mẫu boilerplate
    for cp in _COMPILED_BOILERPLATE:
        if cp.search(stripped):
            return True

    # Khớp dòng nguồn tin đơn độc
    if len(stripped) < 50 and _FOOTER_SOURCE_PATTERN.match(stripped):
        return True

    return False


def clean_article_paragraphs(
    text: str,
    *,
    max_chars: int = 4000,
    min_para_len: int = 15,
) -> str:
    """
    Tinh lọc toàn văn bài viết thành các khối đoạn văn cốt lõi sạch sẽ.
    
    Args:
        text: Chuỗi cleaned_text ban đầu từ Silver hoặc Trafilatura.
        max_chars: Giới hạn ký tự tối đa (Inverted Pyramid) để chống context bloat.
        min_para_len: Độ dài tối thiểu của một đoạn văn hợp lệ.
        
    Returns:
        Chuỗi văn bản sạch chứa các đoạn văn nguyên bản ghép lại bằng 2 dấu xuống dòng.
    """
    if not text:
        return ""

    raw_paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    if not raw_paragraphs:
        return ""

    cleaned_paragraphs: list[str] = []
    current_len = 0

    for para in raw_paragraphs:
        # Bỏ qua đoạn rác / boilerplate
        if is_boilerplate_paragraph(para):
            continue

        # Bỏ qua các mẩu vụn quá ngắn (trừ khi có số liệu % hoặc mã CP)
        if len(para) < min_para_len and not re.search(r"\d+[%]|VN-Index", para):
            continue

        # Kiểm tra ngưỡng trần Inverted Pyramid
        # Nếu đã có ít nhất 2 đoạn văn và thêm đoạn này vượt max_chars thì dừng lấy tiếp
        para_len = len(para)
        if len(cleaned_paragraphs) >= 2 and (current_len + para_len > max_chars):
            break

        cleaned_paragraphs.append(para)
        current_len += para_len + 2  # tính cả \n\n

    # Fallback an toàn: Nếu bộ lọc quá tay lọc hết sạch thì giữ lại text gốc
    if not cleaned_paragraphs:
        return text.strip()

    return "\n\n".join(cleaned_paragraphs)
