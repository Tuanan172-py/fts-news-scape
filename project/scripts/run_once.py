"""
Standalone entry — 1 cycle rồi thoát (quét Bronze + re-derive Silver).

Usage:
    python scripts/run_once.py            # tất cả domain enabled
    python scripts/run_once.py cafef tnck
"""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from src.core.config import load_settings
from src.core.stdio import force_utf8_stdio
from src.db.store import ArticleStore
from src.orchestrator import main
from src.pipeline.derive import rederive_incremental

force_utf8_stdio()

if __name__ == "__main__":
    code = main(["--once"] + [a for a in sys.argv[1:] if a != "all"])
    if code == 0:
        db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
        store = ArticleStore(db_path=db_path)
        rederive_incremental(store)
    sys.exit(code)
