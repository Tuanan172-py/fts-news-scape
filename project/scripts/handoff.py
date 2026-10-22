"""Generate the state hand-off file between two DSH sessions at zero token cost by reading SQLite and the packet files directly."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.article_lane.handoff import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
