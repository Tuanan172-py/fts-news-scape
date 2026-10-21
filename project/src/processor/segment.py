"""Segment Vietnamese text into words (word tokenization)."""

from __future__ import annotations

from loguru import logger

try:
    from pyvi import ViTokenizer

    def seg(text: str) -> list[str]:
        """Split a text into Vietnamese single and compound words.

        Args:
            text: Input text.

        Returns:
            Word tokens.
        """
        if not text:
            return []
        return ViTokenizer.tokenize(text).split()

except ImportError:  # pragma: no cover
    logger.warning("pyvi not installed — falling back to whitespace tokenizer")

    def seg(text: str) -> list[str]:
        """Split a text on whitespace when no segmentation library is available.

        Args:
            text: Input text.

        Returns:
            Whitespace-separated words.
        """
        return text.split() if text else []
