"""Provide CLI subcommands that report the operating state of News-Scape."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ops.console.radar import main  # noqa: E402

if __name__ == "__main__":
    main()
