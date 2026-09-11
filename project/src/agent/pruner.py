"""Tinh lọc đoạn văn và loại bỏ nội dung rác cho bài viết."""
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
    """Kiểm tra đoạn văn bản có thuộc dạng thông tin rác hoặc mẫu cố định hay không.

    Args:
        para: Chuỗi đoạn văn cần kiểm tra.

    Returns:
        True nếu là thông tin rác hoặc định dạng mẫu, ngược lại False.
    """
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


_FINANCIAL_KEYWORDS_RE = re.compile(
    r'(?:\d+[%]|\d+(?:[.,]\d+)?\s*(?:tỷ|triệu|nghìn\s*tỷ|usd|vnd|đồng)|vn-index|lợi\s*nhuận|doanh\s*thu|kế\s*hoạch|tăng\s*trưởng|cổ\s*tức|thị\s*giá|lãi|lỗ|hđqt|nghị\s*quyết)',
    re.IGNORECASE,
)


def clean_article_paragraphs(
    text: str,
    *,
    max_chars: int = 2200,
    min_para_len: int = 15,
    l1_entities: list[str] | None = None,
) -> str:
    """Lọc và giữ lại các đoạn văn cốt lõi của bài viết theo nguyên tắc tháp ngược.

    Args:
        text: Nội dung văn bản thô ban đầu.
        max_chars: Giới hạn ký tự tối đa giữ lại. Mặc định 2200.
        min_para_len: Độ dài tối thiểu của một đoạn văn hợp lệ. Mặc định 15.
        l1_entities: Danh sách thực thể L1 ưu tiên bảo toàn đoạn văn chứa thực thể.

    Returns:
        Văn bản đã làm sạch gồm các đoạn văn nguyên bản ngăn cách bởi hai ký tự xuống dòng.
    """
    if not text:
        return ""

    raw_paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    if not raw_paragraphs:
        return ""

    valid_paras: list[tuple[int, str]] = []
    for idx, para in enumerate(raw_paragraphs):
        # 1. Loại nguyên khối boilerplate
        if is_boilerplate_paragraph(para):
            continue

        # 2. Đoạn quá ngắn thường là caption/tag — nhưng GIỮ nếu mang số liệu thị trường
        if len(para) < min_para_len and not _FINANCIAL_KEYWORDS_RE.search(para):
            continue

        valid_paras.append((idx, para))

    if not valid_paras:
        return text.strip()

    selected_indices: set[int] = set()
    current_len = 0

    # Chuẩn bị pattern thực thể nếu có
    entity_patterns = []
    if l1_entities:
        for e in l1_entities:
            code = e.split(":")[-1].strip()
            if len(code) >= 2:
                entity_patterns.append(re.compile(r'\b' + re.escape(code) + r'\b', re.IGNORECASE))

    # Pass 1: Giữ tối đa 2 đoạn đầu (Sapo / Mở đầu theo Tháp ngược)
    for idx, para in valid_paras[:2]:
        selected_indices.add(idx)
        current_len += len(para) + 2

    # Pass 2: Ưu tiên các đoạn chứa mã CP / thực thể L1
    if entity_patterns:
        for idx, para in valid_paras[2:]:
            if any(ep.search(para) for ep in entity_patterns):
                if current_len + len(para) + 2 <= max_chars + 300:
                    selected_indices.add(idx)
                    current_len += len(para) + 2

    # Pass 3: Điền các đoạn văn kế tiếp theo thứ tự gốc cho tới khi chạm trần max_chars
    for idx, para in valid_paras[2:]:
        if idx in selected_indices:
            continue
        if current_len + len(para) + 2 <= max_chars:
            selected_indices.add(idx)
            current_len += len(para) + 2

    # Tái tạo văn bản theo đúng thứ tự xuất hiện gốc trong bài
    selected_paras = [p for idx, p in valid_paras if idx in selected_indices]
    if not selected_paras:
        return text.strip()

    return "\n\n".join(selected_paras)


