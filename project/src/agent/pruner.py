"""Filter article paragraphs and remove junk content."""
from __future__ import annotations

import re

# Whole paragraphs are dropped; a retained paragraph is never trimmed internally.
_BOILERPLATE_PATTERNS = [
    # Navigation teasers at the end or middle of an article
    r'^(?:bài\s+liên\s+quan|tin\s+cùng\s+chuyên\s+mục|xem\s+thêm\b|đọc\s+tiếp\b|có\s+thể\s+bạn\s+quan\s+tâm|tin\s+khác\b|chuyên\s+mục\s+đặc\s+biệt)',
    # Editorial office and headquarters information
    r'^(?:ban\s+biên\s+tập|tổng\s+biên\s+tập|chịu\s+trách\s+nhiệm\s+nội\s+dung|địa\s+chỉ\s*:\s*tầng|trụ\s+sở\b|tòa\s+nhà\b)',
    # Advertising contact and rate card
    r'^(?:liên\s+hệ\s+quảng\s+cáo|liên\s+hệ\s+dữ\s+liệu|báo\s+giá\s+quảng\s+cáo|quảng\s+cáo\s*:\s*)',
    # Hotline, email, phone and fax
    r'^(?:hotline\s*:|email\s*:|điện\s+thoại\s*:|đt\s*:|máy\s+lẻ\b|fax\s*:)',
    # Press operating licence
    r'(?:giấy\s+phép\s+(?:thiết\s+lập|hoạt\s+động|xuất\s+bản)|sở\s+thông\s+tin\s+và\s+truyền\s+thông)',
    # Copyright
    r'^(?:©\s*copyright|bản\s+quyền\s+thuộc\s+về|toàn\s+bộ\s+bản\s+quyền)',
    # Financial disclaimers and investment warnings
    r'^(?:tuyên\s+bố\s+miễn\s+trừ|khuyến\s+cáo\s+miễn\s+trừ|khuyến\s+cáo\s*:\s*báo\s+cáo\s+này|nhà\s+đầu\s+tư\s+cần\s+cân\s+nhắc|chúng\s+tôi\s+không\s+chịu\s+trách\s+nhiệm\b)',
    # Company information box and company profile at the foot of an article
    r'^(?:thông\s+tin\s+doanh\s+nghiệp\b|hồ\s+sơ\s+doanh\s+nghiệp\b|tổng\s+quan\s+về\s+[A-Z0-9]+|tiền\s+thân\s+là\s+tập\s+đoàn\b)',
    # Photo and chart captions
    r'^(?:ảnh|hình\s+ảnh|đồ\s+thị|biểu\s+đồ|nguồn\s+ảnh|ảnh\s+chụp)\s*:',
    # UI widgets (font size, share, follow, print)
    r'^(?:chọn\s+cỡ\s+chữ|chia\s+sẻ\s+bài\s+viết|theo\s+dõi\s+chúng\s+tôi\s+trên|in\s+bài\s+viết)',
    # Lines made only of separator characters
    r'^[\s\|\:\-]+$',
]

_COMPILED_BOILERPLATE = [re.compile(p, re.IGNORECASE) for p in _BOILERPLATE_PATTERNS]

# Source credit at the end of an article (`Theo CafeF`, `Nguồn: ...`) or an author/reporter byline.
# Applied only to short paragraphs (<= 100 characters) so real content is not dropped.
_FOOTER_SOURCE_PATTERN = re.compile(
    r'^(?:theo\s+(?:báo\s+)?(?:hose|hnx|upcom|cafef|vietstock|vneconomy|ttxvn|reuters|bloomberg|dân\s+trí|đầu\s+tư|tiền\s+phong|chứng\s+khoán)\b|nguồn\s*:|(?:bài\s+và\s+ảnh|phóng\s+viên|biên\s+tập|tác\s+giả)\s*:).*$',
    re.IGNORECASE,
)


def is_boilerplate_paragraph(para: str) -> bool:
    """Check whether a paragraph is junk or fixed boilerplate.

    Args:
        para: Paragraph text to check.

    Returns:
        True if the paragraph is junk or boilerplate, otherwise False.
    """
    stripped = para.strip()
    if not stripped:
        return True

    # Stray characters and leftover separators
    if len(stripped) <= 3 and not stripped.isalnum():
        return True

    for cp in _COMPILED_BOILERPLATE:
        if cp.search(stripped):
            return True

    # Source or author line at the end of an article; counted only when <= 100 characters.
    if len(stripped) <= 100 and _FOOTER_SOURCE_PATTERN.match(stripped):
        return True

    return False
