"""Track how far back an API listing must page so an outage leaves no hole (rule 10)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))
STATE_KEY = "catchup_ok:{name}"
MARGIN = timedelta(hours=2)
FIRST_RUN = timedelta(days=1)
MAX_BACK = timedelta(days=14)


def _now(now: datetime | None) -> datetime:
    """Return `now`, or the current Vietnam time."""
    return now or datetime.now(VN_TZ)


def catchup_cutoff(store, name: str, *, now: datetime | None = None) -> datetime:
    """Return the oldest publication time the next listing run must reach.

    The cutoff is the start of the last complete run minus a margin, so a machine that was
    off for three days pages back three days. It never reaches past `MAX_BACK`.

    Args:
        store: ArticleStore holding `pipeline_state`.
        name: Scraper name.
        now: Reference time.

    Returns:
        Timezone-aware cutoff.
    """
    now = _now(now)
    raw = store.get_state(STATE_KEY.format(name=name))
    try:
        last = datetime.fromisoformat(raw) if raw else now - FIRST_RUN
    except ValueError:
        last = now - FIRST_RUN
    if last.tzinfo is None:
        last = last.replace(tzinfo=VN_TZ)
    return max(last - MARGIN, now - MAX_BACK)


def mark_complete(store, name: str, started_at: datetime) -> None:
    """Record that a listing run starting at `started_at` read everything back to its cutoff.

    Call it only when no page failed and no cap was hit; otherwise the next run keeps the
    old cutoff and reads the hole again.

    Args:
        store: ArticleStore holding `pipeline_state`.
        name: Scraper name.
        started_at: Start time of the run.
    """
    store.set_state(STATE_KEY.format(name=name), started_at.isoformat(timespec="seconds"))


def page_reaches(dates: list[str], cutoff: datetime) -> bool:
    """Tell whether a page reaches back to the cutoff.

    Args:
        dates: ISO publication times of the items on the page; empty strings are ignored.
        cutoff: Timezone-aware cutoff.

    Returns:
        True when the oldest dated item is older than the cutoff, or when no item has a date.
    """
    parsed = []
    for d in dates:
        try:
            dt = datetime.fromisoformat(d)
        except (TypeError, ValueError):
            continue
        parsed.append(dt if dt.tzinfo else dt.replace(tzinfo=VN_TZ))
    return not parsed or min(parsed) < cutoff
