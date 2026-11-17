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
        tier1_count: Pending articles matching Tier-1 watchlist or urgent macro signals.
        oldest_tier1_fetched_at: Fetch time of the longest-waiting Tier-1 pending article.
        priority_targets: Pending on-demand priority refresh targets recorded in `ops.db`.
    """

    per_date: list[tuple[str, int]] = field(default_factory=list)
    oldest_fetched_at: datetime | None = None
    backlog_all: int | None = None
    tier1_count: int = 0
    oldest_tier1_fetched_at: datetime | None = None
    priority_targets: list[str] = field(default_factory=list)

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

    def oldest_tier1_age_minutes(self, now: datetime | None = None) -> float | None:
        """Compute the age of the longest-waiting Tier-1 pending article.

        Args:
            now: Comparison time.

        Returns:
            Number of minutes, or None when no Tier-1 article is pending.
        """
        if self.oldest_tier1_fetched_at is None:
            return None
        return ((now or now_vn()) - self.oldest_tier1_fetched_at).total_seconds() / 60.0


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


def _load_priority_targets(ops_db: Path | None) -> list[str]:
    """Read pending on-demand refresh targets from `ops.db` when present.

    Args:
        ops_db: Path to `ops.db`, or None.

    Returns:
        Deduplicated list of pending target strings.
    """
    if ops_db is None or not Path(ops_db).is_file():
        return []
    try:
        conn = sqlite3.connect(f"file:{Path(ops_db).as_posix()}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return []
    try:
        has_tbl = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ops_priority_requests'"
        ).fetchone()
        if not has_tbl:
            return []
        rows = conn.execute(
            "SELECT target FROM ops_priority_requests WHERE status = 'pending' ORDER BY id"
        ).fetchall()
        return list(dict.fromkeys(str(r[0]).strip() for r in rows if r and str(r[0]).strip()))
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def read_pending(db_path: Path, lookback_days: int, *, now: datetime | None = None,
                 with_backlog: bool = False,
                 exclude: set[str] | None = None,
                 ops_db: Path | None = None) -> SensorReading:
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
        ops_db: Optional path to `ops.db` for checking priority refresh requests.

    Returns:
        The SensorReading.
    """
    from scripts.article_pack import load_candidates, tier_of, watchlist_universe

    reading = SensorReading()
    resolved_ops_db = Path(ops_db) if ops_db else (Path(db_path).parent / "ops.db")
    reading.priority_targets = _load_priority_targets(resolved_ops_db)

    reg = None
    watched: set[str] = set()
    industries: set[str] = set()
    try:
        from src.agent.entities import load_registry
        reg = load_registry()
        watched, industries = watchlist_universe(reg)
    except Exception:
        reg = None

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        oldest: datetime | None = None
        oldest_t1: datetime | None = None
        t1_ids: list[str] = []
        for d in scope_dates(lookback_days, now):
            rows = load_candidates(conn, date=d, limit=1_000_000, only_pending=True,
                                   exclude=exclude, with_content=True)
            reading.per_date.append((d, len(rows)))
            ids = [r["article_id"] for r in rows]
            if reg is not None:
                for r in rows:
                    tier_num, _ = tier_of(r["title"] or "", reg, watched, industries)
                    if tier_num == 1:
                        t1_ids.append(r["article_id"])
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                marks = ",".join("?" * len(chunk))
                row = conn.execute(f"SELECT MIN(fetched_at) FROM articles "
                                   f"WHERE url_title_hash IN ({marks})", chunk).fetchone()
                ts = parse_iso(row[0]) if row else None
                if ts and (oldest is None or ts < oldest):
                    oldest = ts
        for i in range(0, len(t1_ids), 500):
            chunk = t1_ids[i:i + 500]
            marks = ",".join("?" * len(chunk))
            row = conn.execute(f"SELECT MIN(fetched_at) FROM articles "
                               f"WHERE url_title_hash IN ({marks})", chunk).fetchone()
            ts = parse_iso(row[0]) if row else None
            if ts and (oldest_t1 is None or ts < oldest_t1):
                oldest_t1 = ts
        reading.oldest_fetched_at = oldest
        reading.tier1_count = len(t1_ids)
        reading.oldest_tier1_fetched_at = oldest_t1
        if with_backlog:
            reading.backlog_all = len(load_candidates(conn, date=None, limit=10_000_000,
                                                      only_pending=True, exclude=exclude,
                                                      with_content=False, exclude_thin=False))
    finally:
        conn.close()
    return reading


def pick_backlog_date(db_path: Path, lookback_days: int, *, now: datetime | None = None,
                      exclude: set[str] | None = None,
                      as_range: bool = False) -> tuple[str, int] | None:
    """Find the newest date outside the monitored scope that still has processable pending articles.

    Thin articles fail the DoD gate deterministically, so a date holding only thin articles
    is skipped; otherwise the backlog lane would open empty waves for it forever.

    Args:
        db_path: Path of `monocle.db`.
        lookback_days: Monitored scope; its dates are left to the normal rules.
        now: Reference time.
        exclude: Article identifiers to skip (in another wave or out of attempts).
        as_range: Return `OLDEST..NEWEST` over every out-of-scope backlog date instead of
            one date, so a wave fills its whole limit, newest articles first, across sparse
            dates. One date per wave needed about 700 waves for the 2026-11 backlog.

    Returns:
        (date or range, pending count before the thin filter), or None when the backlog
        is empty.
    """
    from scripts.article_pack import is_thin, load_candidates, row_paragraphs

    scope = set(scope_dates(lookback_days, now))
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        # One candidate query for the whole backlog. A query per date held the sensor lock
        # for about 3 minutes with 400 sparse dates (2026-11-13).
        rows = load_candidates(conn, date=None, limit=10_000_000, only_pending=True,
                               exclude=exclude, with_content=True, exclude_thin=False)
        day_of: dict[str, str] = {}
        ids = [r["article_id"] for r in rows]
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            marks = ",".join("?" * len(chunk))
            for h, d in conn.execute(
                    "SELECT url_title_hash, substr(COALESCE(NULLIF(published_at, ''), fetched_at), "
                    f"1, 10) FROM articles WHERE url_title_hash IN ({marks})", chunk):
                if d and d not in scope:
                    day_of[h] = d
        per_date: dict[str, int] = {}
        by_date: dict[str, list] = {}
        for r in rows:
            d = day_of.get(r["article_id"])
            if d:
                per_date[d] = per_date.get(d, 0) + 1
                by_date.setdefault(d, []).append(r)
        for d in sorted(per_date, reverse=True):
            # The packer's own test: readable paragraphs that are not thin. `load_candidates`
            # fails open on bodies that yield no paragraphs, which opened empty waves.
            if any((p := row_paragraphs(r)) and not is_thin(p) for r in by_date[d]):
                if as_range:
                    return f"{min(per_date)}..{d}", sum(n for k, n in per_date.items() if k <= d)
                return d, per_date[d]
    finally:
        conn.close()
    return None


def backlog_window(now: datetime, cfg: dict) -> bool:
    """Tell whether the backlog lane may run now.

    Args:
        now: Time to check.
        cfg: The `sensor.backlog` section: `enabled`, `hours` [start, end) that may wrap
            past midnight, and `weekend_all_day`.

    Returns:
        True when backlog waves are allowed.
    """
    if not cfg.get("enabled"):
        return False
    if cfg.get("weekend_all_day") and now.weekday() >= 5:
        return True
    h0, h1 = (cfg.get("hours") or [19, 7])[:2]
    return h0 <= now.hour or now.hour < h1 if h0 > h1 else h0 <= now.hour < h1


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
    if reading.priority_targets:
        shown = ", ".join(reading.priority_targets[:3])
        return True, "T_PRI", f"Yêu cầu làm tươi ưu tiên ({shown}; {n} bài chờ)."
    threshold = int(cfg.get("threshold", 100))
    if n >= threshold:
        return True, "T1", f"Đủ ngưỡng khối lượng ({n} ≥ {threshold} bài)."
    th0, th1 = (cfg.get("tier1_hours") or [8, 16])[:2]
    if reading.tier1_count > 0 and th0 <= now.hour < th1:
        t1_thresh = int(cfg.get("tier1_threshold", 15))
        if reading.tier1_count >= t1_thresh:
            return (
                True,
                "T2_TIER1",
                f"Đủ ngưỡng nhanh Tier-1 ({reading.tier1_count} ≥ {t1_thresh} bài ưu tiên).",
            )
        t1_age = reading.oldest_tier1_age_minutes(now)
        t1_max_age = float(cfg.get("tier1_max_age_minutes", 25))
        if t1_age is not None and t1_age > t1_max_age:
            return (
                True,
                "T2_TIER1",
                f"Bài Tier-1 chờ {t1_age:.0f} phút > {t1_max_age:.0f} phút ({reading.tier1_count} bài ưu tiên).",
            )
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
