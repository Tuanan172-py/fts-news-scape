"""Run duplicate clustering and then write the inheritance result in one step, with zero tokens."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from src.pipeline import story_cluster
from src.pipeline.inherit import apply_inheritance


def refresh(conn: sqlite3.Connection, days: int = 3,
            today: datetime | None = None) -> dict[str, int]:
    """Cluster the most recent days and then write the inheritance result.

    Args:
        conn: Write connection to the operational DB.
        days: Number of most recent days to cluster, including today.
        today: "Today" reference of the clustering and inheritance window; None means the
            current time.

    Returns:
        Merged dict of clustering and inheritance statistics; inheritance keys carry the
        `inherit_` prefix.
    """
    stats = story_cluster.run(conn, days=days, today=today)
    inh = apply_inheritance(conn, now=today)
    return {**stats, **{f"inherit_{k}": v for k, v in inh.items()}}
