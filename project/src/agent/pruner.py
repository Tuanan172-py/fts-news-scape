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

# Loại theo NGUYÊN KHỐI đoạn văn — không bao giờ cắt tỉa bên trong đoạn được giữ lại.
_BOILERPLATE_PATTERNS = [
    # Teaser điều hướng cuối bài / giữa bài
    r'^(?:bài\s+liên\s+quan|tin\s+cùng\s+chuyên\s+mục|xem\s+thêm\b|đọc\s+tiếp\b|có\s+thể\s+bạn\s+quan\s+tâm|tin\s+khác\b|chuyên\s+mục\s+đặc\s+biệt)',
    # Thông tin tòa soạn / trụ sở
    r'^(?:ban\s+biên\s+tập|tổng\s+biên\s+tập|chịu\s+trách\s+nhiệm\s+nội\s+dung|địa\s+chỉ\s*:\s*tầng|trụ\s+sở\b|tòa\s+nhà\b)',
    # Liên hệ quảng cáo / báo giá
    r'^(?:liên\s+hệ\s+quảng\s+cáo|liên\s+hệ\s+dữ\s+liệu|báo\s+giá\s+quảng\s+cáo|quảng\s+cáo\s*:\s*)',
    # Hotline / email / điện thoại / fax
    r'^(?:hotline\s*:|email\s*:|điện\s+thoại\s*:|đt\s*:|máy\s+lẻ\b|fax\s*:)',
    # Giấy phép hoạt động báo chí
    r'(?:giấy\s+phép\s+(?:thiết\s+lập|hoạt\s+động|xuất\s+bản)|sở\s+thông\s+tin\s+và\s+truyền\s+thông)',
    # Bản quyền
    r'^(?:©\s*copyright|bản\s+quyền\s+thuộc\s+về|toàn\s+bộ\s+bản\s+quyền)',
    # Widget giao diện (cỡ chữ, chia sẻ, theo dõi, in bài)
    r'^(?:chọn\s+cỡ\s+chữ|chia\s+sẻ\s+bài\s+viết|theo\s+dõi\s+chúng\s+tôi\s+trên|in\s+bài\s+viết)',
    # Dòng chỉ gồm ký tự phân cách
    r'^[\s\|\:\-]+$',
]

_COMPILED_BOILERPLATE = [re.compile(p, re.IGNORECASE) for p in _BOILERPLATE_PATTERNS]

# Dòng ghi nguồn cuối bài ("Theo CafeF", "Nguồn: ..."). Chỉ loại khi đoạn NGẮN, để không
# nuốt nhầm một đoạn nội dung thật vô tình mở đầu bằng chữ "Theo".
_FOOTER_SOURCE_PATTERN = re.compile(
    r'^(?:theo\s+(?:hose|hnx|upcom|cafef|vietstock|vneconomy|ttxvn|reuters|bloomberg|dân\s+trí|đầu\s+tư|tiền\s+phong)|nguồn\s*:)\b.*$',
    re.IGNORECASE,
)


def is_boilerplate_paragraph(para: str) -> bool:
    """Kiểm tra một đoạn văn có phải là rác thông tin / boilerplate không."""
    stripped = para.strip()
    if not stripped:
        return True

    # Ký tự lẻ / dấu phân cách sót lại
    if len(stripped) <= 3 and not stripped.isalnum():
        return True

    for cp in _COMPILED_BOILERPLATE:
        if cp.search(stripped):
            return True

    # Dòng nguồn cuối bài — chỉ tính khi đoạn đủ ngắn
    if len(stripped) < 50 and _FOOTER_SOURCE_PATTERN.match(stripped):
        return True

    return False


def clean_article_paragraphs(text: str, *, max_chars: int = 4000, min_para_len: int = 15) -> str:
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
        # 1. Loại nguyên khối boilerplate
        if is_boilerplate_paragraph(para):
            continue

        # 2. Đoạn quá ngắn thường là caption/tag — nhưng GIỮ nếu mang số liệu thị trường
        if len(para) < min_para_len and not re.search(r'\d+[%]|VN-Index', para):
            continue

        # 3. Trần ký tự (Inverted Pyramid) — chỉ cắt khi đã có tối thiểu 2 đoạn
        para_len = len(para)
        if len(cleaned_paragraphs) >= 2 and current_len + para_len > max_chars:
            break

        cleaned_paragraphs.append(para)
        current_len += para_len + 2          # +2 cho '\n\n' khi ghép

    # Lọc sạch quá tay thì thà trả nguyên bản còn hơn trả rỗng
    if not cleaned_paragraphs:
        return text.strip()

    return "\n\n".join(cleaned_paragraphs)
