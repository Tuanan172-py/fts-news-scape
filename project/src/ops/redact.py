"""Mask secrets in text before it is written to events, alerts, logs or prompts."""

from __future__ import annotations

import re
from typing import Any

MASK = "***"

_PATTERNS = (
    # Telegram bot token, including when it sits in a URL such as `.../bot<token>/sendMessage`.
    re.compile(r"(?<!\d)\d{6,12}:[A-Za-z0-9_-]{30,}"),
    # healthchecks.io ping URL: the identifier after the domain is the secret.
    re.compile(r"(?<=hc-ping\.com/)[A-Za-z0-9_-]{8,}(?:/[A-Za-z0-9_-]+)?"),
    # API keys of the form `sk-...` (OpenRouter, OpenAI) and Bearer headers.
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)(?<=bearer )[A-Za-z0-9._~+/=-]{16,}"),
)


def redact(text: str | None) -> str | None:
    """Replace every secret-like string with the mask.

    Args:
        text: Text to mask, possibly None.

    Returns:
        The masked text, or None when the input is None.
    """
    if not text:
        return text
    out = str(text)
    for pat in _PATTERNS:
        out = pat.sub(MASK, out)
    return out


def redact_data(value: Any) -> Any:
    """Mask secrets in every string of a nested dict or list structure.

    Args:
        value: Any value.

    Returns:
        A masked copy; non-string values are kept unchanged.
    """
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_data(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_data(v) for v in value]
    return value
