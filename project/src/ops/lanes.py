"""Phân luồng đợt: mỗi đợt thuộc đúng một luồng, mỗi luồng tối đa một đợt đang chạy."""

from __future__ import annotations

AUTO = "auto"
BACKLOG = "backlog"
BENCH = "bench"
LANES = (AUTO, BACKLOG, BENCH)

# Luồng theo giá trị cột `ops_waves.trigger`. Giá trị lạ thuộc luồng auto để không bỏ sót đợt của daemon.
_TRIGGER_LANE = {
    "T1": AUTO, "T2": AUTO, "T3": AUTO, "retry": AUTO, "manual": AUTO,
    "backlog": BACKLOG, "adhoc": BACKLOG,
    "bench": BENCH,
}

LANE_LABEL = {AUTO: "Luồng tự động", BACKLOG: "Luồng bài tồn", BENCH: "Luồng thử nghiệm"}


def lane_of(trigger: str | None) -> str:
    """Trả về luồng của một đợt theo luật kích hoạt.

    Args:
        trigger: Giá trị cột `trigger` của đợt (T1, T2, T3, retry, backlog, adhoc, bench).

    Returns:
        Một trong auto, backlog, bench.
    """
    return _TRIGGER_LANE.get(trigger or "", AUTO)
