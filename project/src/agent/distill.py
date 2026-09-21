"""Chắt lọc đoạn văn tất định cho packet gửi mô hình.

Module này thay trần cắt tỉa cơ học 2.200 ký tự cũ. Nó tồn tại vì hai lý do độc lập:

**Bảo toàn trích dẫn.** Cơ chế trích dẫn theo chỉ số đoạn chỉ đúng khi mỗi phần tử
trong mảng trả về là **chuỗi con nguyên văn** của văn bản gốc. Vì vậy quy tắc bất
biến ở đây là chỉ được **bỏ trọn một đoạn**, tuyệt đối không cắt, không nối, không
sửa chữ, không đổi thứ tự. Hàm :func:`distill` tự khẳng định điều này trước khi trả về.

**Kiểm soát chi phí.** Khi mọi bài đều được xử lý đầy đủ cả nội dung, kích thước
packet của từng bài quyết định trực tiếp tổng chi phí của cả hệ. Thuật toán vì thế
phải có trần cứng và thứ tự bỏ xác định, nếu không thì con số dự toán trước mỗi đợt
không có cơ sở và chốt tự chia lô cũng mất ý nghĩa.
"""
from __future__ import annotations

import re

from src.agent.pruner import is_boilerplate_paragraph

# Quy đổi ký tự sang token cho tiếng Việt. Đo trên kho bài thật của dự án.
CHARS_PER_TOKEN = 3

# Trần mềm cho phần nội dung của một bài, tính bằng token. **0 nghĩa là không cắt.**
#
# Trần này từng để 900 với lý do tiết kiệm token đầu vào. Số đo 2026-09-21 trên 600
# bài thật đã bác bỏ chính lý do ấy: sau các bộ lọc cơ học, một bài nặng trung bình
# 1.542 token, nên một đợt trăm bài chỉ chiếm 15% cửa sổ một triệu. Đầu vào chưa
# cache lại rẻ hơn đầu ra năm mươi lần. Đổi lại, trần 900 đã bỏ **46% nội dung**
# trước khi mô hình kịp đọc — tức code đang quyết định mô hình được đọc gì, trái với
# nguyên tắc nội dung do LLM xử lý.
#
# Vẫn giữ tham số để dùng tay khi cần; chỉ bỏ nó khỏi đường chạy mặc định.
DEFAULT_MAX_TOKENS_PER_ARTICLE = 0

MIN_PARAGRAPH_CHARS = 40

# Trần ký tự cho MỘT đoạn. Công cụ đọc của DSH cắt mỗi dòng ở 2.000 ký tự
# (`readMaxLineLength`), mà packet ghi mỗi đoạn một dòng, nên đoạn dài hơn ngưỡng này
# sẽ bị cắt cụt âm thầm. Đo trên 4.493 đoạn thật: dài nhất 954 ký tự, không đoạn nào
# chạm trần. Đo lại trên 14.199 dòng thật ngày 21/09: đúng **một** dòng vượt ngưỡng,
# dài nhất 2.059 ký tự — tức nó có chạm, dù hiếm.
#
# Trước đây chạm thì bỏ nguyên đoạn. Nay **tách** đoạn tại ranh giới câu thay vì bỏ:
# mỗi mảnh vẫn là chuỗi con nguyên văn nên bất biến nguyên văn được giữ, mà không mất
# chữ nào. Bỏ một đoạn dài là mất đúng phần thường mang nhiều thông tin nhất.
MAX_PARAGRAPH_CHARS = 1800

_QUANT_RE = re.compile(
    r"(?:\d+(?:[.,]\d+)?\s*%"
    r"|\d+(?:[.,]\d+)?\s*(?:tỷ|triệu|nghìn|ngàn)\s*(?:đồng|usd|vnd)?"
    r"|\d+(?:[.,]\d+)?\s*(?:usd|vnd|đồng)"
    r"|lợi\s*nhuận|doanh\s*thu|biên\s*lợi\s*nhuận|kqkd|nợ\s*xấu|cổ\s*tức"
    r"|tăng\s*trưởng|thị\s*giá|vốn\s*hóa|eps|roe)",
    re.IGNORECASE,
)

_VOICE_RE = re.compile(
    r"(?:ông\s+[A-ZĐÀ-Ỹ]|bà\s+[A-ZĐÀ-Ỹ]|chủ\s*tịch|tổng\s*giám\s*đốc|giám\s*đốc"
    r"|phát\s*biểu|cho\s*biết|nhận\s*định|khẳng\s*định"
    r"|nghị\s*quyết|quyết\s*định\s*số|thông\s*tư|nghị\s*định|luật\s|xử\s*phạt)",
    re.IGNORECASE,
)


def estimate_tokens(text: str) -> int:
    """Ước lượng số token của một đoạn văn bản tiếng Việt.

    Args:
        text: Đoạn văn bản cần ước lượng.

    Returns:
        Số token ước tính.
    """
    return len(text) // CHARS_PER_TOKEN


def _rank(paragraph: str) -> int:
    """Chấm hạng ưu tiên giữ lại của một đoạn văn.

    Hạng cao hơn được giữ trước khi chạm trần. Thứ tự này cố định nên kích thước
    packet là hàm xác định của đầu vào.

    Args:
        paragraph: Nội dung đoạn văn.

    Returns:
        2 khi đoạn chứa số liệu định lượng, 1 khi chứa phát ngôn hoặc sự kiện pháp lý,
        0 cho các trường hợp còn lại.
    """
    if _QUANT_RE.search(paragraph):
        return 2
    if _VOICE_RE.search(paragraph):
        return 1
    return 0


def split_long_paragraph(para: str, limit: int = MAX_PARAGRAPH_CHARS) -> list[str]:
    """Tách một đoạn quá dài thành nhiều mảnh, mỗi mảnh vẫn nguyên văn.

    Cắt ưu tiên tại ranh giới câu để mảnh còn đọc được; không tìm được ranh giới nào
    hợp lý thì cắt đúng trần. Mọi mảnh đều là chuỗi con của đoạn gốc, nên bất biến
    nguyên văn của cả khâu chắt lọc vẫn đứng.

    Args:
        para: Đoạn văn cần tách.
        limit: Trần ký tự cho mỗi mảnh.

    Returns:
        Danh sách mảnh theo đúng thứ tự gốc.
    """
    out: list[str] = []
    start = 0
    while len(para) - start > limit:
        window = para[start:start + limit]
        cut = max(window.rfind(". "), window.rfind("! "),
                  window.rfind("? "), window.rfind("; "))
        cut = cut + 1 if cut > limit // 3 else limit
        piece = para[start:start + cut].strip()
        if piece:
            out.append(piece)
        start += cut
    tail = para[start:].strip()
    if tail:
        out.append(tail)
    return out


def split_paragraphs(text: str) -> list[str]:
    """Tách văn bản thành các đoạn sạch, giữ nguyên văn từng đoạn.

    Args:
        text: Nội dung bài viết đã chuẩn hóa.

    Returns:
        Danh sách đoạn văn theo đúng thứ tự gốc, đã loại đoạn rác và đoạn quá ngắn.
    """
    if not text:
        return []
    out: list[str] = []
    for raw in text.splitlines():
        para = raw.strip()
        if not para or is_boilerplate_paragraph(para):
            continue
        if len(para) < MIN_PARAGRAPH_CHARS and not _QUANT_RE.search(para):
            continue
        if len(para) > MAX_PARAGRAPH_CHARS:
            out.extend(split_long_paragraph(para))
            continue
        out.append(para)
    return out


def distill(text: str, *, max_tokens: int = DEFAULT_MAX_TOKENS_PER_ARTICLE) -> list[str]:
    """Chọn tập con các đoạn văn giá trị cao, giữ nguyên văn và nguyên thứ tự.

    Thuật toán cố định gồm bốn bước: luôn giữ đoạn mở đầu; xếp hạng các đoạn còn lại
    theo tín hiệu định lượng rồi tới phát ngôn; thêm dần theo hạng cho tới khi chạm
    trần; cuối cùng sắp lại theo thứ tự xuất hiện gốc. Khi vượt trần thì bỏ nguyên
    đoạn hạng thấp nhất, không bao giờ cắt ngang một đoạn.

    Args:
        text: Nội dung bài viết đã chuẩn hóa.
        max_tokens: Trần token cho phần nội dung của bài.

    Returns:
        Danh sách đoạn văn đã chọn, mỗi phần tử là chuỗi con nguyên văn của `text`.

    Raises:
        AssertionError: Khi một đoạn trả về không phải chuỗi con nguyên văn của đầu vào.
    """
    paragraphs = split_paragraphs(text)
    if not paragraphs:
        return []
    if max_tokens <= 0:
        return paragraphs

    budget = max_tokens
    chosen: set[int] = set()

    # Đoạn mở đầu luôn được giữ: theo cấu trúc tháp ngược của báo chí, nó mang phần lớn
    # nội dung sự kiện. Giữ cả khi nó một mình đã vượt trần, vì bài không có đoạn nào
    # thì mô hình không có gì để trích dẫn.
    chosen.add(0)
    used = estimate_tokens(paragraphs[0])

    remaining = sorted(
        range(1, len(paragraphs)),
        key=lambda i: (-_rank(paragraphs[i]), i),
    )
    for idx in remaining:
        cost = estimate_tokens(paragraphs[idx])
        if used + cost > budget:
            continue
        chosen.add(idx)
        used += cost

    result = [paragraphs[i] for i in sorted(chosen)]
    for para in result:
        assert para in text, "đoạn chắt lọc phải là chuỗi con nguyên văn của bài gốc"
    return result


def distill_stats(text: str, *, max_tokens: int = DEFAULT_MAX_TOKENS_PER_ARTICLE) -> dict:
    """Chắt lọc và kèm theo số liệu phục vụ dự toán và biểu đồ phân bố.

    Args:
        text: Nội dung bài viết đã chuẩn hóa.
        max_tokens: Trần token cho phần nội dung của bài.

    Returns:
        Từ điển gồm danh sách đoạn đã chọn và các số đo trước sau khi chắt lọc.
    """
    paragraphs = split_paragraphs(text)
    kept = distill(text, max_tokens=max_tokens)
    return {
        "paragraphs": kept,
        "n_before": len(paragraphs),
        "n_after": len(kept),
        "tokens_before": sum(estimate_tokens(p) for p in paragraphs),
        "tokens_after": sum(estimate_tokens(p) for p in kept),
    }
