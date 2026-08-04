"""
Word segmentation wrapper — tokenizer-agnostic seam.

pyvi primary (cài nhẹ trên Windows). underthesea nâng cấp sau nếu cần
(cùng interface). Fallback cuối: whitespace split.
"""

from __future__ import annotations

from loguru import logger

try:
    from pyvi import ViTokenizer

    def seg(text: str) -> list[str]:
        """Tách từ tiếng Việt. Từ ghép nối bằng '_' (vd 'chứng_khoán')."""
        if not text:
            return []
        return ViTokenizer.tokenize(text).split()

except ImportError:  # pragma: no cover
    logger.warning("pyvi not installed — falling back to whitespace tokenizer")

    def seg(text: str) -> list[str]:
        return text.split() if text else []
