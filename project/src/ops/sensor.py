"""Measure articles awaiting analysis and decide when to open an Article Lane wave."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from src.ops.store import VN_TZ, now_vn, parse_iso


@dataclass
class SensorReading:
    """Measurement of pending articles within the monitored date scope.

    Attributes:
        per_date: Pending article count per publication date, oldest first.
        oldest_fetched_at: Fetch time of the longest-waiting pending article.
        backlog_all: Total pending articles across all dates (for reporting only).
    """

    per_date: list[tuple[str, int]] = field(default_factory=list)
    oldest_fetched_at: datetime | None = None
    backlog_all: int | None = None

    @property
    def total(self) -> int:
        """Return the total pending articles within the monitored scope."""
        return sum(n for _, n in self.per_date)

    @property
    def target_date(self) -> str | None:
        """Return the oldest date that still has pending articles, which the next wave will take."""
        for d, n in self.per_date:
            if n > 0:
                return d
        return None

    def oldest_age_minutes(self, now: datetime | None = None) -> float | None:
        """Compute the age of the longest-waiting pending article.

        Args:
            now: Comparison time.

        Returns:
            Number of minutes, or None when nothing is pending.
        """
        if self.oldest_fetched_at is None:
            return None
        return ((now or now_vn()) - self.oldest_fetched_at).total_seconds() / 60.0


def scope_dates(lookback_days: int, now: datetime | None = None) -> list[str]:
    """List the publication dates in the monitored scope, oldest first.

    Args:
        lookback_days: Number of days to look back besides today.
        now: Reference time.

    Returns:
        List of YYYY-MM-DD strings.
    """
    today = (now or now_vn()).date()
    return [(today - timedelta(days=i)).isoformat()
            for i in range(max(0, int(lookback_days)), -1, -1)]


def read_pending(db_path: Path, lookback_days: int, *, now: datetime | None = None,
                 with_backlog: bool = False,
                 exclude: set[str] | None = None) -> SensorReading:
    """Count pending articles with the same selector as `article_pack.load_candidates`.

    Articles in `exclude` (belonging to an unfinished wave or out of attempts) are not
    counted, including in the age of the longest-waiting article, so the T2 age rule does not
    fire endlessly because of an article that never passes the DoD gate.

    Args:
        db_path: Path of `monocle.db`.
        lookback_days: Number of days to look back besides today.
        now: Reference time.
        with_backlog: Also count the total pending articles across all dates.
        exclude: Article identifiers to skip.

    Returns:
        The SensorReading.
    """
    from scripts.article_pack import load_candidates

    reading = SensorReading()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        oldest: datetime | None = None
        for d in scope_dates(lookback_days, now):
            rows = load_candidates(conn, date=d, limit=1_000_000, only_pending=True,
                                   exclude=exclude, with_content=True)
            reading.per_date.append((d, len(rows)))
            ids = [r["article_id"] for r in rows]
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                marks = ",".join("?" * len(chunk))
                row = conn.execute(f"SELECT MIN(fetched_at) FROM articles "
                                   f"WHERE url_title_hash IN ({marks})", chunk).fetchone()
                ts = parse_iso(row[0]) if row else None
                if ts and (oldest is None or ts < oldest):
                    oldest = ts
        reading.oldest_fetched_at = oldest
        if with_backlog:
            reading.backlog_all = len(load_candidates(conn, date=None, limit=10_000_000,
                                                      only_pending=True, exclude=exclude,
                                                      with_content=False, exclude_thin=False))
    finally:
        conn.close()
    return reading


def in_windows(now: datetime, windows: list[str]) -> str | None:
    """Check whether a time falls inside a `HH:MM-HH:MM` window.

    Args:
        now: Time to check.
        windows: List of time windows.

    Returns:
        The matching window string, or None.
    """
    minutes = now.hour * 60 + now.minute
    for w in windows:
        try:
            a, b = w.split("-")
            ah, am = (int(x) for x in a.split(":"))
            bh, bm = (int(x) for x in b.split(":"))
        except ValueError:
            continue
        if ah * 60 + am <= minutes <= bh * 60 + bm:
            return w
    return None


def cooldown_active(until: str | None, *, now: datetime | None = None) -> bool:
    """Report whether the sensor is still in its cooldown after a failed wave.

    Args:
        until: Cooldown end time in ISO form, or None when absent.
        now: Time to evaluate, defaulting to the present.

    Returns:
        True when `until` is still in the future.
    """
    return bool(until) and (now or now_vn()) < parse_iso(until)


def decide(reading: SensorReading, cfg: dict, *, now: datetime | None = None,
           force: bool = False) -> tuple[bool, str, str]:
    """Apply the three trigger rules: T1 volume, T2 age, T3 time window.

    Args:
        reading: Pending-article measurement.
        cfg: The `sensor` section of the configuration.
        now: Evaluation time.
        force: Skip the rules and open a wave when articles are pending.

    Returns:
        Triple (open a wave, rule code, reason).
    """
    now = now or now_vn()
    if now.tzinfo is None:
        now = now.replace(tzinfo=VN_TZ)
    n = reading.total
    if n <= 0:
        return False, "", "Không có bài chờ trong phạm vi theo dõi."
    if force:
        return True, "manual", f"Người vận hành yêu cầu ({n} bài chờ)."
    threshold = int(cfg.get("threshold", 100))
    if n >= threshold:
        return True, "T1", f"Đủ ngưỡng khối lượng ({n} ≥ {threshold} bài)."
    h0, h1 = (cfg.get("age_rule_hours") or [0, 24])[:2]
    age = reading.oldest_age_minutes(now)
    max_age = float(cfg.get("max_age_minutes", 90))
    if age is not None and age > max_age and h0 <= now.hour < h1:
        return True, "T2", f"Bài chờ lâu nhất {age:.0f} phút > {max_age:.0f} phút ({n} bài)."
    window = in_windows(now, cfg.get("flush_windows") or [])
    if window:
        return True, "T3", f"Khung giờ vét {window} ({n} bài)."
    age_txt = f", lâu nhất {age:.0f} phút" if age is not None else ""
    return False, "", f"Chưa đủ điều kiện ({n}/{threshold} bài{age_txt})."
