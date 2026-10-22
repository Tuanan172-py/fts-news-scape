"""Pack articles into worker packets with priority tiering and a cost estimate."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.article_lane.pack import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
