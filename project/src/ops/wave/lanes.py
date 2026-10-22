"""Assign waves to lanes, where each wave belongs to exactly one lane and each lane runs at most one wave."""

from __future__ import annotations

AUTO = "auto"
BACKLOG = "backlog"
BENCH = "bench"
LANES = (AUTO, BACKLOG, BENCH)

# Lane by value of the `ops_waves.trigger` column. Unknown values belong to the auto lane so no daemon wave is missed.
_TRIGGER_LANE = {
    "T1": AUTO, "T2": AUTO, "T3": AUTO, "retry": AUTO, "manual": AUTO,
    "backlog": BACKLOG, "adhoc": BACKLOG,
    "bench": BENCH,
}

LANE_LABEL = {AUTO: "Luồng tự động", BACKLOG: "Luồng bài tồn", BENCH: "Luồng thử nghiệm"}


def lane_of(trigger: str | None) -> str:
    """Return the lane of a wave from its trigger rule.

    Args:
        trigger: Value of the wave `trigger` column (T1, T2, T3, retry, backlog, adhoc, bench).

    Returns:
        One of auto, backlog, bench.
    """
    return _TRIGGER_LANE.get(trigger or "", AUTO)
