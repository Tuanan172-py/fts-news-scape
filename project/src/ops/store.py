"""Store operations events, alerts, breakers, state, waves and commands in `ops.db`."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from src.ops.lanes import lane_of
from src.core.redact import redact, redact_data
from src.telemetry.trace import SPAN_SCHEMA
from src.db.connect import open_rw

VN_TZ = timezone(timedelta(hours=7))

LEVELS = ("debug", "info", "warn", "error", "critical")
ACTIVE_WAVE_STATUSES = ("SENSED", "PREFLIGHT", "PREPARED", "ANALYZING", "REPAIRING",
                        "ANALYZED", "FINISHING")
# Waves in these statuses have finished their lifecycle; their articles are no longer reserved.
RELEASED_WAVE_STATUSES = ("DONE", "CANCELLED")

SCHEMA = """
CREATE TABLE IF NOT EXISTS ops_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  level TEXT NOT NULL,
  actor TEXT NOT NULL,
  wave_id TEXT,
  step TEXT,
  kind TEXT NOT NULL,
  message TEXT NOT NULL,
  data_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_ops_events_ts ON ops_events(ts);
CREATE INDEX IF NOT EXISTS idx_ops_events_wave ON ops_events(wave_id, ts);
CREATE TABLE IF NOT EXISTS ops_alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  severity TEXT NOT NULL,
  dedup_key TEXT,
  text TEXT NOT NULL,
  buttons_json TEXT,
  repeats INTEGER NOT NULL DEFAULT 1,
  sent_at TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_ops_alerts_unsent ON ops_alerts(sent_at, id);
CREATE INDEX IF NOT EXISTS idx_ops_alerts_dedup ON ops_alerts(dedup_key, created_at);
CREATE TABLE IF NOT EXISTS provider_breakers (
  provider TEXT PRIMARY KEY,
  state TEXT NOT NULL DEFAULT 'CLOSED',
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  last_class TEXT,
  opened_at TEXT,
  reopen_at TEXT,
  reason TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS ops_state (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS ops_waves (
  wave_id TEXT PRIMARY KEY,
  workflow_id TEXT,
  status TEXT NOT NULL,
  step TEXT,
  trigger TEXT,
  target_date TEXT,
  n_articles INTEGER,
  level TEXT,
  provider TEXT,
  attempt INTEGER NOT NULL DEFAULT 0,
  opened_at TEXT NOT NULL,
  updated_at TEXT,
  progress_at TEXT,
  finished_at TEXT,
  reason TEXT,
  resume_on_breaker INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ops_waves_status ON ops_waves(status, opened_at);
CREATE TABLE IF NOT EXISTS ops_wave_articles (
  wave_id TEXT NOT NULL,
  article_id TEXT NOT NULL,
  PRIMARY KEY (wave_id, article_id)
);
CREATE INDEX IF NOT EXISTS idx_ops_wave_articles_article ON ops_wave_articles(article_id);
CREATE TABLE IF NOT EXISTS ops_article_attempts (
  article_id TEXT PRIMARY KEY,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_wave TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS ops_proposals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  dedup_key TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  evidence_json TEXT,
  impact REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'open',
  decided_at TEXT,
  story_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_ops_proposals_status ON ops_proposals(status, impact);
CREATE TABLE IF NOT EXISTS ops_commands (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  actor TEXT NOT NULL,
  text TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  result TEXT,
  processed_at TEXT
);
"""


def now_vn() -> datetime:
    """Return the current time in Vietnam time.

    Returns:
        A datetime object with the +07:00 time zone.
    """
    return datetime.now(VN_TZ)


def iso(dt: datetime | None = None) -> str:
    """Format a timestamp as an ISO string to the second.

    Args:
        dt: Timestamp to format. Defaults to the present.

    Returns:
        ISO 8601 string with a time zone.
    """
    return (dt or now_vn()).isoformat(timespec="seconds")


def parse_iso(text: str | None) -> datetime | None:
    """Parse an ISO string, assigning Vietnam time when the string has no time zone.

    Args:
        text: ISO string or None.

    Returns:
        A timezone-aware datetime, or None when it cannot be parsed.
    """
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=VN_TZ)


class OpsStore:
    """Access `ops.db` safely across the multiple threads of the daemon.

    Each operation opens a short connection with `busy_timeout`, so the Telegram thread, the
    workflow thread and the main loop write concurrently without sharing a connection object.

    Attributes:
        path: Path of the `ops.db` file.
        log_dir: Directory for the JSONL copy of events, or None to disable.
        dedup_minutes: Window for merging alerts with the same key.
    """

    def __init__(self, path: Path, *, log_dir: Path | None = None,
                 dedup_minutes: int = 30) -> None:
        """Create the store and ensure the schema exists.

        Args:
            path: Path of the `ops.db` file.
            log_dir: JSONL log directory.
            dedup_minutes: Alert merge window.
        """
        self.path = Path(path)
        self.log_dir = Path(log_dir) if log_dir else None
        self.dedup_minutes = dedup_minutes
        self._jsonl_lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)
            c.executescript(SPAN_SCHEMA)

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        """Open a short connection, committing on clean exit and rolling back on error.

        Yields:
            SQLite connection whose `row_factory` is Row.
        """
        c = open_rw(self.path, timeout=10, row_factory=True, busy_timeout_ms=10000)
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    # ── events ───────────────────────────────────────────────────────────────
    def emit(self, kind: str, message: str, *, level: str = "info", actor: str = "daemon",
             wave_id: str | None = None, step: str | None = None,
             data: dict[str, Any] | None = None) -> int:
        """Write an event to `ops_events` and to the daily JSONL copy.

        Args:
            kind: Event kind, for example `wave.opened`.
            message: Short description in Vietnamese.
            level: Severity level in LEVELS.
            actor: Component that raised the event.
            wave_id: Related wave identifier.
            step: Wave step.
            data: Attached data.

        Returns:
            Identifier of the event just written.
        """
        ts = iso()
        message = redact(message) or ""
        data = redact_data(data) if data else None
        payload = json.dumps(data, ensure_ascii=False, default=str) if data else None
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO ops_events(ts, level, actor, wave_id, step, kind, message, data_json) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (ts, level, actor, wave_id, step, kind, message, payload))
            event_id = int(cur.lastrowid)
        if self.log_dir is not None:
            row = {"id": event_id, "ts": ts, "level": level, "actor": actor,
                   "wave_id": wave_id, "step": step, "kind": kind, "message": message,
                   "data": data}
            try:
                self.log_dir.mkdir(parents=True, exist_ok=True)
                with self._jsonl_lock, open(self.log_dir / f"{ts[:10]}.jsonl", "a",
                                            encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            except OSError:
                pass
        return event_id

    def events(self, *, limit: int = 30, wave_id: str | None = None,
               min_level: str | None = None, after_id: int = 0) -> list[sqlite3.Row]:
        """Read the newest events, ordered by ascending time.

        Args:
            limit: Maximum number of events.
            wave_id: Filter by wave.
            min_level: Filter to this level and above.
            after_id: Only events with a greater identifier.

        Returns:
            List of event rows.
        """
        where, params = ["id > ?"], [after_id]
        if wave_id:
            where.append("wave_id = ?")
            params.append(wave_id)
        if min_level in LEVELS:
            where.append("level IN (%s)" % ",".join("?" * len(LEVELS[LEVELS.index(min_level):])))
            params.extend(LEVELS[LEVELS.index(min_level):])
        sql = (f"SELECT * FROM ops_events WHERE {' AND '.join(where)} "
               f"ORDER BY id DESC LIMIT ?")
        with self.conn() as c:
            rows = c.execute(sql, [*params, limit]).fetchall()
        return list(reversed(rows))

    # ── alerts (outbox) ──────────────────────────────────────────────────────
    def alert(self, severity: str, text: str, *, dedup_key: str | None = None,
              buttons: list[list[tuple[str, str]]] | None = None) -> int | None:
        """Put an alert in the outbox, merging it with an alert of the same key within the window.

        Args:
            severity: One of `critical`, `error`, `warn`, `info`, `digest`.
            text: Message body.
            dedup_key: Merge key. The same key within `dedup_minutes` only increments the counter.
            buttons: Button rows as [[(label, command), ...], ...].

        Returns:
            Identifier of the new alert, or None when merged into an older alert.
        """
        now = now_vn()
        text = redact(text) or ""
        with self.conn() as c:
            if dedup_key:
                since = iso(now - timedelta(minutes=self.dedup_minutes))
                row = c.execute(
                    "SELECT id FROM ops_alerts WHERE dedup_key = ? AND created_at >= ? "
                    "ORDER BY id DESC LIMIT 1", (dedup_key, since)).fetchone()
                if row:
                    c.execute("UPDATE ops_alerts SET repeats = repeats + 1 WHERE id = ?",
                              (row["id"],))
                    return None
            cur = c.execute(
                "INSERT INTO ops_alerts(created_at, severity, dedup_key, text, buttons_json) "
                "VALUES (?,?,?,?,?)",
                (iso(now), severity, dedup_key, text,
                 json.dumps(buttons, ensure_ascii=False) if buttons else None))
            return int(cur.lastrowid)

    def unsent_alerts(self, limit: int = 20) -> list[sqlite3.Row]:
        """Fetch unsent alerts, oldest first.

        Args:
            limit: Maximum number of alerts.

        Returns:
            List of alert rows.
        """
        with self.conn() as c:
            return c.execute("SELECT * FROM ops_alerts WHERE sent_at IS NULL "
                             "ORDER BY id LIMIT ?", (limit,)).fetchall()

    def mark_alert(self, alert_id: int, *, sent: bool, error: str | None = None) -> None:
        """Record the delivery result of one alert.

        Args:
            alert_id: Alert identifier.
            sent: True when delivery succeeded.
            error: Delivery error, if any.
        """
        with self.conn() as c:
            if sent:
                c.execute("UPDATE ops_alerts SET sent_at = ?, attempts = attempts + 1, "
                          "last_error = NULL WHERE id = ?", (iso(), alert_id))
            else:
                c.execute("UPDATE ops_alerts SET attempts = attempts + 1, last_error = ? "
                          "WHERE id = ?", (redact(error), alert_id))

    # ── key/value state ──────────────────────────────────────────────────────
    def get_state(self, key: str, default: str | None = None) -> str | None:
        """Read one state value.

        Args:
            key: State key.
            default: Value returned when the key is absent.

        Returns:
            The value string or `default`.
        """
        with self.conn() as c:
            row = c.execute("SELECT value FROM ops_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_state(self, key: str, value: str | None) -> None:
        """Write one state value; None deletes the key.

        Args:
            key: State key.
            value: Value string or None.
        """
        with self.conn() as c:
            if value is None:
                c.execute("DELETE FROM ops_state WHERE key = ?", (key,))
            else:
                c.execute("INSERT INTO ops_state(key, value, updated_at) VALUES (?,?,?) "
                          "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                          "updated_at = excluded.updated_at", (key, value, iso()))

    # ── waves ────────────────────────────────────────────────────────────────
    def upsert_wave(self, wave_id: str, **fields: Any) -> None:
        """Create or update the row of one wave.

        Args:
            wave_id: Wave identifier.
            **fields: Columns to write.
        """
        fields["updated_at"] = iso()
        with self.conn() as c:
            exists = c.execute("SELECT 1 FROM ops_waves WHERE wave_id = ?",
                               (wave_id,)).fetchone()
            if exists:
                sets = ", ".join(f"{k} = ?" for k in fields)
                c.execute(f"UPDATE ops_waves SET {sets} WHERE wave_id = ?",
                          [*fields.values(), wave_id])
            else:
                fields.setdefault("status", "SENSED")
                fields.setdefault("opened_at", iso())
                cols = ", ".join(["wave_id", *fields])
                marks = ", ".join("?" * (len(fields) + 1))
                c.execute(f"INSERT INTO ops_waves({cols}) VALUES ({marks})",
                          [wave_id, *fields.values()])

    def wave(self, wave_id: str) -> sqlite3.Row | None:
        """Read the row of one wave.

        Args:
            wave_id: Wave identifier.

        Returns:
            The wave row or None.
        """
        with self.conn() as c:
            return c.execute("SELECT * FROM ops_waves WHERE wave_id = ?",
                             (wave_id,)).fetchone()

    def waves(self, limit: int = 10) -> list[sqlite3.Row]:
        """Read the newest waves.

        Args:
            limit: Maximum number of waves.

        Returns:
            List of wave rows, newest first.
        """
        with self.conn() as c:
            return c.execute("SELECT * FROM ops_waves ORDER BY opened_at DESC LIMIT ?",
                             (limit,)).fetchall()

    def active_waves(self, lane: str | None = None) -> list[sqlite3.Row]:
        """List the running waves, newest first.

        Args:
            lane: Only waves of this lane (auto, backlog, bench); None takes every lane.

        Returns:
            List of wave rows in an active status.
        """
        marks = ",".join("?" * len(ACTIVE_WAVE_STATUSES))
        with self.conn() as c:
            rows = c.execute(f"SELECT * FROM ops_waves WHERE status IN ({marks}) "
                             "ORDER BY opened_at DESC", ACTIVE_WAVE_STATUSES).fetchall()
        return [r for r in rows if lane is None or lane_of(r["trigger"]) == lane]

    def active_wave(self, lane: str | None = None) -> sqlite3.Row | None:
        """Return the newest running wave, if any.

        Args:
            lane: Only consider waves of this lane; None considers every lane.

        Returns:
            The wave row in an active status, or None.
        """
        rows = self.active_waves(lane)
        return rows[0] if rows else None

    def parked_for_breaker(self) -> list[sqlite3.Row]:
        """List PARKED waves that are waiting for the provider to recover.

        Returns:
            List of wave rows, oldest first.
        """
        with self.conn() as c:
            return c.execute("SELECT * FROM ops_waves WHERE status = 'PARKED' "
                             "AND resume_on_breaker = 1 ORDER BY opened_at").fetchall()

    # ── article reservation per wave ─────────────────────────────────────────
    def record_wave_articles(self, wave_id: str, article_ids: list[str]) -> int:
        """Record the article set of a wave and increment each article attempt count exactly once.

        Calling again for the same wave (a rerun after a crash) does not increment the attempt count again.

        Args:
            wave_id: Wave identifier.
            article_ids: Identifiers of the articles in the wave.

        Returns:
            Number of new articles recorded for the wave.
        """
        added = 0
        now = iso()
        with self.conn() as c:
            for aid in article_ids:
                cur = c.execute("INSERT OR IGNORE INTO ops_wave_articles(wave_id, article_id) "
                                "VALUES (?,?)", (wave_id, aid))
                if cur.rowcount:
                    added += 1
                    c.execute("INSERT INTO ops_article_attempts(article_id, attempts, "
                              "last_wave, updated_at) VALUES (?,1,?,?) "
                              "ON CONFLICT(article_id) DO UPDATE SET "
                              "attempts = attempts + 1, last_wave = excluded.last_wave, "
                              "updated_at = excluded.updated_at", (aid, wave_id, now))
        return added

    def bump_attempts(self, article_ids: list[str], wave_id: str) -> int:
        """Increment the attempt count of articles just packed for repair, once per article per round.

        Args:
            article_ids: Identifiers of the articles repaired in this round.
            wave_id: Identifier of the wave being repaired.

        Returns:
            Number of articles incremented.
        """
        now = iso()
        with self.conn() as c:
            for aid in article_ids:
                c.execute("INSERT INTO ops_article_attempts(article_id, attempts, "
                          "last_wave, updated_at) VALUES (?,1,?,?) "
                          "ON CONFLICT(article_id) DO UPDATE SET "
                          "attempts = attempts + 1, last_wave = excluded.last_wave, "
                          "updated_at = excluded.updated_at", (aid, wave_id, now))
        return len(article_ids)

    def reserved_article_ids(self) -> set[str]:
        """List articles that belong to a wave with an unfinished lifecycle (running, PARKED, FAILED).

        Returns:
            Set of article identifiers that must not be packed into another wave.
        """
        marks = ",".join("?" * len(RELEASED_WAVE_STATUSES))
        with self.conn() as c:
            rows = c.execute(
                "SELECT DISTINCT a.article_id FROM ops_wave_articles a "
                "JOIN ops_waves w ON w.wave_id = a.wave_id "
                f"WHERE w.status NOT IN ({marks})", RELEASED_WAVE_STATUSES).fetchall()
        return {r[0] for r in rows}

    def exhausted_article_ids(self, max_attempts: int) -> set[str]:
        """List articles that have been packed the maximum number of attempts.

        Args:
            max_attempts: Maximum number of attempts per article.

        Returns:
            Set of article identifiers that must not be retried automatically.
        """
        with self.conn() as c:
            rows = c.execute("SELECT article_id FROM ops_article_attempts WHERE attempts >= ?",
                             (int(max_attempts),)).fetchall()
        return {r[0] for r in rows}

    def excluded_article_ids(self, max_attempts: int) -> set[str]:
        """Combine reserved articles and articles that are out of attempts.

        Args:
            max_attempts: Maximum number of attempts per article.

        Returns:
            Set of article identifiers that the sensor and the packer must skip.
        """
        return self.reserved_article_ids() | self.exhausted_article_ids(max_attempts)

    # ── console commands ─────────────────────────────────────────────────────
    def enqueue_command(self, text: str, actor: str = "console") -> int:
        """Put a command in the inbox for the daemon to process.

        Args:
            text: Command such as `/pause`.
            actor: Command source.

        Returns:
            Command identifier.
        """
        with self.conn() as c:
            cur = c.execute("INSERT INTO ops_commands(created_at, actor, text) VALUES (?,?,?)",
                            (iso(), actor, text))
            return int(cur.lastrowid)

    def pending_commands(self) -> list[sqlite3.Row]:
        """Fetch unprocessed commands, oldest first.

        Returns:
            List of command rows.
        """
        with self.conn() as c:
            return c.execute("SELECT * FROM ops_commands WHERE status = 'pending' "
                             "ORDER BY id").fetchall()

    def finish_command(self, command_id: int, result: str, status: str = "done") -> None:
        """Record the processing result of one command.

        Args:
            command_id: Command identifier.
            result: Result text.
            status: Final status.
        """
        with self.conn() as c:
            c.execute("UPDATE ops_commands SET status = ?, result = ?, processed_at = ? "
                      "WHERE id = ?", (status, result, iso(), command_id))

    def command(self, command_id: int) -> sqlite3.Row | None:
        """Read one command by identifier.

        Args:
            command_id: Command identifier.

        Returns:
            The command row or None.
        """
        with self.conn() as c:
            return c.execute("SELECT * FROM ops_commands WHERE id = ?",
                             (command_id,)).fetchone()
