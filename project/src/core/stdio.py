"""Configure UTF-8 standard streams for Windows consoles."""

from __future__ import annotations

import sys


def force_utf8_stdio() -> None:
    """Reconfigure stdout and stderr to UTF-8 to avoid character encoding errors on Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
