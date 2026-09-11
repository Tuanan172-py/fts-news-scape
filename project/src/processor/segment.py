"""Tiện ích phân đoạn từ tiếng Việt (word tokenization)."""

from __future__ import annotations

from loguru import logger

try:
    from pyvi import ViTokenizer

    def seg(text: str) -> list[str]:
        """Phân tách chuỗi văn bản thành danh sách từ đơn và từ ghép tiếng Việt.

        Args:
            text: Chuỗi văn bản đầu vào.

        Returns:
            Danh sách các token từ vựng.
        """
        if not text:
            return []
        return ViTokenizer.tokenize(text).split()

except ImportError:  # pragma: no cover
    logger.warning("pyvi not installed — falling back to whitespace tokenizer")

    def seg(text: str) -> list[str]:
        """Phân tách chuỗi văn bản theo khoảng trắng khi không có thư viện phân đoạn.

        Args:
            text: Chuỗi văn bản đầu vào.

        Returns:
            Danh sách các từ đơn giản.
        """
        return text.split() if text else []
