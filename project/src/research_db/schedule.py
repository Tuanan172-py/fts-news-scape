"""Decide when the production news lakehouse publishes: fixed Research slots, catch-up after downtime, and express pushes for urgent news."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

SLOT_KEY = "research:slot:{day}:{name}"
LAST_PUBLISH_KEY = "research:last_publish_at"


@dataclass
class Decision:
    """A publish to run now.

    Attributes:
        reason: Trigger recorded in the manifest, for example `slot:sau-phien` or `express`.
        slot_keys: State keys of the slots this publish satisfies.
    """

    reason: str
    slot_keys: list[str] = field(default_factory=list)


def due_slots(now: datetime, slots: list[dict], is_done: Callable[[str], bool],
              lookback_hours: float = 24) -> list[tuple[datetime, str, str]]:
    """List slots whose time has passed within the look-back window and that have not run.

    Args:
        now: Current Vietnam time, timezone-aware.
        slots: Slot configs with `name` and `at` (`HH:MM`).
        is_done: Returns True when a slot state key is already recorded.
        lookback_hours: Oldest slot age still caught up after downtime.

    Returns:
        (slot time, slot name, state key) tuples, oldest first.
    """
    out = []
    for back in (1, 0):
        day = (now - timedelta(days=back)).date()
        for s in slots:
            hh, mm = (int(x) for x in str(s["at"]).split(":"))
            at = now.replace(year=day.year, month=day.month, day=day.day, hour=hh, minute=mm,
                             second=0, microsecond=0)
            key = SLOT_KEY.format(day=day.isoformat(), name=s["name"])
            if at <= now and now - at <= timedelta(hours=lookback_hours) and not is_done(key):
                out.append((at, s["name"], key))
    return sorted(out)


def decide(now: datetime, cfg: dict, *, is_done: Callable[[str], bool], wave_active: bool,
           last_publish_at: datetime | None, urgent_since: Callable[[datetime], int]
           ) -> Decision | None:
    """Pick the publish to run now, if any.

    A due slot waits for a running wave to finish, up to `wait_wave_max_minutes` after the
    slot time, so the slot carries the articles that wave analyses. Several due slots (the
    machine was off) collapse into one catch-up publish. Between slots, urgent analyses that
    passed DoD since the last publish trigger an express publish, at most once per
    `express.min_interval_minutes`.

    Args:
        now: Current Vietnam time, timezone-aware.
        cfg: The `research_publish` configuration section.
        is_done: Returns True when a slot state key is already recorded.
        wave_active: Whether an analysis wave is running.
        last_publish_at: Time of the last successful publish, if any.
        urgent_since: Counts urgent DoD-passed analyses after a time.

    Returns:
        Decision, or None when nothing should run now.
    """
    due = due_slots(now, cfg.get("slots") or [], is_done,
                    float(cfg.get("catchup_lookback_hours", 24)))
    if due:
        at, name, _ = due[-1]
        wait = timedelta(minutes=float(cfg.get("wait_wave_max_minutes", 15)))
        if wave_active and now - at < wait:
            return None
        reason = f"slot:{name}" if len(due) == 1 else f"catchup:{name}+{len(due) - 1}"
        return Decision(reason, [k for _, _, k in due])
    express = cfg.get("express") or {}
    if not express.get("enabled") or last_publish_at is None:
        return None
    if now - last_publish_at < timedelta(minutes=float(express.get("min_interval_minutes", 30))):
        return None
    return Decision("express") if urgent_since(last_publish_at) > 0 else None
