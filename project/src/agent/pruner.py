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
    """Keep the core paragraphs of an article following the inverted-pyramid principle.

    Args:
        text: Raw article text.
        max_chars: Maximum number of characters to keep.
        min_para_len: Minimum length of a valid paragraph.
        l1_entities: L1 entities; paragraphs that mention them are kept with priority.

    Returns:
        Cleaned text of the original paragraphs separated by blank lines.
    """
    if not text:
        return ""

    raw_paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    if not raw_paragraphs:
        return ""

    valid_paras: list[tuple[int, str]] = []
    for idx, para in enumerate(raw_paragraphs):
        # Drop whole boilerplate paragraphs.
        if is_boilerplate_paragraph(para):
            continue

        # Very short paragraphs are usually captions or tags; keep them if they carry market figures.
        if len(para) < min_para_len and not _FINANCIAL_KEYWORDS_RE.search(para):
            continue

        valid_paras.append((idx, para))

    if not valid_paras:
        return text.strip()

    selected_indices: set[int] = set()
    current_len = 0

    # Build entity patterns when entities are given.
    entity_patterns = []
    if l1_entities:
        for e in l1_entities:
            code = e.split(":")[-1].strip()
            if len(code) >= 2:
                entity_patterns.append(re.compile(r'\b' + re.escape(code) + r'\b', re.IGNORECASE))

    # Pass 1: keep up to the first 2 paragraphs (lead of the inverted pyramid).
    for idx, para in valid_paras[:2]:
        selected_indices.add(idx)
        current_len += len(para) + 2

    # Pass 2: prioritize paragraphs that mention stock tickers or L1 entities.
    if entity_patterns:
        for idx, para in valid_paras[2:]:
            if any(ep.search(para) for ep in entity_patterns):
                if current_len + len(para) + 2 <= max_chars + 300:
                    selected_indices.add(idx)
                    current_len += len(para) + 2

    # Pass 3: fill the following paragraphs in original order until max_chars is reached.
    for idx, para in valid_paras[2:]:
        if idx in selected_indices:
            continue
        if current_len + len(para) + 2 <= max_chars:
            selected_indices.add(idx)
            current_len += len(para) + 2

    # Rebuild the text in original paragraph order.
    selected_paras = [p for idx, p in valid_paras if idx in selected_indices]
    if not selected_paras:
        return text.strip()

    return "\n\n".join(selected_paras)


