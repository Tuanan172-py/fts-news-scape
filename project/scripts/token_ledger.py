"""Record and report measured DSH runtime token usage in the `token_ledger` table."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.article_lane.ledger import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
