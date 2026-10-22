"""Run a whole processing wave of the article lane with a single command."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ops.wave.article_run import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
