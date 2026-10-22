"""Distill article paragraphs deterministically for packets sent to the model."""
from __future__ import annotations

import re

from src.agent.packet.pruner import is_boilerplate_paragraph

# Design constraints:
# - Citation integrity: paragraph-index citations are valid only when every returned
#   element is a verbatim substring of the source text. The only allowed operation is
#   dropping a whole paragraph (no cutting, joining, rewording or reordering).
#   distill() asserts this before returning.
# - Cost control: packet size per article drives total cost, so the algorithm needs a
#   hard ceiling and a deterministic drop order for pre-run estimates and batch sizing.

# Characters-to-tokens ratio for Vietnamese, measured on the project article corpus.
CHARS_PER_TOKEN = 3

# Soft ceiling on the content of one article, in tokens. 0 means no truncation.
#
# A ceiling of 900 was dropped after a 2026-09-21 measurement on 600 real articles: after
# the mechanical filters an article averages 1,542 tokens, so a batch of one hundred uses
# only 15% of a one-million-token window, and uncached input is fifty times cheaper than
# output. The 900 ceiling dropped 46% of the content before the model read it, so code
# decided what the model could read, against the rule that the LLM processes content.
#
# The parameter stays available for manual use and is off on the default path.
DEFAULT_MAX_TOKENS_PER_ARTICLE = 0

MIN_PARAGRAPH_CHARS = 40

# Character ceiling for ONE paragraph. The DSH read tool truncates each line at 2,000
# characters (`readMaxLineLength`) and packets write one paragraph per line, so a longer
# paragraph is silently truncated. Measured on 14,199 real lines on 21/09: exactly one line
# exceeded the limit (2,059 characters).
#
# A paragraph over the ceiling is split at sentence boundaries instead of dropped: each
# piece is still a verbatim substring, so the verbatim invariant holds and no text is lost.
MAX_PARAGRAPH_CHARS = 1600

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
    """Estimate the token count of a Vietnamese text.

    Args:
        text: Text to estimate.

    Returns:
        Estimated token count.
    """
    return len(text) // CHARS_PER_TOKEN


def _rank(paragraph: str) -> int:
    """Rank the retention priority of a paragraph.

    A higher rank is kept first when the ceiling is reached. The order is fixed, so the
    packet size is a deterministic function of the input.

    Args:
        paragraph: Paragraph text.

    Returns:
        2 if the paragraph has quantitative figures, 1 if it has a statement or legal
        event, 0 otherwise.
    """
    if _QUANT_RE.search(paragraph):
        return 2
    if _VOICE_RE.search(paragraph):
        return 1
    return 0


def split_long_paragraph(para: str, limit: int = MAX_PARAGRAPH_CHARS) -> list[str]:
    """Split an overlong paragraph into pieces that stay verbatim.

    Cuts prefer sentence boundaries so pieces remain readable; when no reasonable
    boundary exists the cut falls at the limit. Every piece is a substring of the source
    paragraph, so the verbatim invariant of the distillation holds.

    Args:
        para: Paragraph to split.
        limit: Character ceiling per piece.

    Returns:
        Pieces in original order.
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
    """Split text into clean paragraphs, keeping each paragraph verbatim.

    Args:
        text: Normalized article text.

    Returns:
        Paragraphs in original order, without junk and too-short paragraphs.
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
    """Select the high-value paragraph subset, verbatim and in original order.

    The fixed algorithm has four steps: always keep the opening paragraph; rank the rest
    by quantitative signals, then statements; add them by rank until the ceiling is
    reached; finally restore the original order. Over the ceiling, whole lowest-ranked
    paragraphs are dropped and a paragraph is never cut.

    Args:
        text: Normalized article text.
        max_tokens: Token ceiling for the article content; 0 or less keeps all paragraphs.

    Returns:
        Selected paragraphs, each a verbatim substring of `text`.

    Raises:
        AssertionError: If a returned paragraph is not a verbatim substring of the input.
    """
    paragraphs = split_paragraphs(text)
    if not paragraphs:
        return []
    if max_tokens <= 0:
        return paragraphs

    budget = max_tokens
    chosen: set[int] = set()

    # The opening paragraph is always kept: in the inverted pyramid of news writing it
    # carries most of the event. It is kept even when it alone exceeds the ceiling, because
    # with no paragraph the model has nothing to cite.
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
    """Distill the text and return statistics for estimates and distribution charts.

    Args:
        text: Normalized article text.
        max_tokens: Token ceiling for the article content.

    Returns:
        Dict with the selected paragraphs and the counts before and after distillation.
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
