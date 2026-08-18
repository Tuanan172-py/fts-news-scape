"""
Stdio helper — ép stdout/stderr sang UTF-8 (Windows).

`print()` tiếng Việt/emoji/`→`/`—` qua Task Scheduler bị redirect vào file dùng
cp1252 → UnicodeEncodeError làm crash script. Gọi `force_utf8_stdio()` ngay đầu
mọi script/entry để tránh. Idempotent, không raise.
"""

from __future__ import annotations

import sys


def force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
