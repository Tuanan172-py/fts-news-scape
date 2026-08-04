"""
Standalone entry — 1 cycle rồi thoát (delegate sang orchestrator).

Usage:
    python scripts/run_once.py            # tất cả domain enabled
    python scripts/run_once.py cafef tnck
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestrator import main

if __name__ == "__main__":
    sys.exit(main(["--once"] + [a for a in sys.argv[1:] if a != "all"]))
