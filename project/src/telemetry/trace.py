"""Record the spans of a wave into `ops_spans` and do nothing when the environment variables are missing."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from src.core import pipeline_spec
from src.db.connect import open_rw

ENV_DB = "OPS_TRACE_DB"
ENV_WAVE = "OPS_TRACE_WAVE"
ENV_PARENT = "OPS_TRACE_PARENT"

VN_TZ = timezone(timedelta(hours=7))
REGISTRY_PATH = Path(__file__).resolve().parents[3] / ".agents" / "registry.yaml"

SPAN_SCHEMA = """
CREATE TABLE IF NOT EXISTS ops_spans (
  span_id TEXT PRIMARY KEY,
  trace_id TEXT NOT NULL,
  parent_id TEXT,
  kind TEXT NOT NULL,
  name TEXT NOT NULL,
  actor_id TEXT,
  skill TEXT,
  entrypoint TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  attrs_json TEXT,
  input_ref TEXT,
  output_ref TEXT
);
CREATE INDEX IF NOT EXISTS idx_ops_spans_trace ON ops_spans(trace_id, started_at);
CREATE INDEX IF NOT EXISTS idx_ops_spans_actor ON ops_spans(actor_id, started_at);
CREATE INDEX IF NOT EXISTS idx_ops_spans_parent ON ops_spans(parent_id);
"""

# Scripts that run inside `article_run.py` and their matching agents in the registry.
SCRIPT_ACTORS = pipeline_spec.script_actors()


def _now() -> str:
    return datetime.now(VN_TZ).isoformat(timespec="milliseconds")


@lru_cache(maxsize=1)
def _registry() -> dict[str, dict]:
    """Read `registry.yaml` once and return a dict keyed by agent id."""
    try:
        import yaml

        data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
        return {a["id"]: a for a in data.get("agents", []) if isinstance(a, dict) and "id" in a}
    except Exception:  # noqa: BLE001 — a missing registry must not break the wave
        return {}


def registry_info(actor_id: str | None) -> tuple[str | None, str | None]:
    """Look up the skill and entrypoint of an agent.

    Args:
        actor_id: Agent identifier in the registry.

    Returns:
        Pair (skill, entrypoint), None where absent.
    """
    if not actor_id:
        return None, None
    a = _registry().get(actor_id) or {}
    skill = a.get("skill")
    if skill:
        skill = Path(str(skill)).parent.name or str(skill)
    entry = a.get("entrypoint") or a.get("cli")
    return skill, (str(entry)[:120] if entry else None)


def _connect(path: str | Path) -> sqlite3.Connection:
    return open_rw(path, timeout=5, busy_timeout_ms=5000)


class Tracer:
    """Write spans to `ops.db`; every write error is swallowed so the wave is unaffected.

    Attributes:
        db_path: Path of `ops.db`.
        trace_id: Wave identifier.
        parent_id: Default parent span of new spans.
    """

    def __init__(self, db_path: str | Path, trace_id: str, parent_id: str | None = None) -> None:
        """Bind the tracer to a wave.

        Args:
            db_path: Path of `ops.db`.
            trace_id: Wave identifier.
            parent_id: Default parent span.
        """
        self.db_path = str(db_path)
        self.trace_id = trace_id
        self.parent_id = parent_id
        self._ready = False

    def _ensure(self, conn: sqlite3.Connection) -> None:
        if not self._ready:
            conn.executescript(SPAN_SCHEMA)
            self._ready = True

    def begin(self, name: str, kind: str, actor_id: str | None = None, *,
              span_id: str | None = None, parent_id: str | None = ..., **attrs: Any) -> str | None:
        """Open a span in the `running` status; reopening the same `span_id` overwrites it.

        Args:
            name: Span name.
            kind: workflow, step, script, agent, tool, gate or human.
            actor_id: Agent identifier in the registry.
            span_id: Fixed span identifier (so a rerun after a crash does not duplicate).
            parent_id: Parent span; the default uses the default parent, None makes a root span.
            **attrs: Initial attributes.

        Returns:
            The span identifier, or None when the write fails.
        """
        try:
            sid = span_id or f"{self.trace_id}.{kind}.{int(time.time() * 1000)}"
            pid = self.parent_id if parent_id is ... else parent_id
            skill, entry = registry_info(actor_id)
            entry = attrs.pop("entrypoint", None) or entry
            with _connect(self.db_path) as conn:
                self._ensure(conn)
                conn.execute(
                    "INSERT OR REPLACE INTO ops_spans(span_id, trace_id, parent_id, kind, name, "
                    "actor_id, skill, entrypoint, started_at, status, attrs_json) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (sid, self.trace_id, pid, kind, name, actor_id, skill, entry, _now(),
                     "running", json.dumps(attrs, ensure_ascii=False, default=str) if attrs else None))
            return sid
        except Exception:  # noqa: BLE001
            return None

    def finish(self, span_id: str | None, status: str = "ok", **attrs: Any) -> None:
        """Close a span, merging new attributes into the existing ones.

        Args:
            span_id: Span identifier from `begin`.
            status: ok, fail, timeout, skipped, parked, cancelled or interrupted.
            **attrs: Additional attributes.
        """
        if not span_id:
            return
        input_ref = attrs.pop("input_ref", None)
        output_ref = attrs.pop("output_ref", None)
        try:
            with _connect(self.db_path) as conn:
                row = conn.execute("SELECT attrs_json FROM ops_spans WHERE span_id = ?",
                                   (span_id,)).fetchone()
                merged = json.loads(row[0]) if row and row[0] else {}
                merged.update(attrs)
                conn.execute(
                    "UPDATE ops_spans SET ended_at = ?, status = ?, attrs_json = ?, "
                    "input_ref = COALESCE(?, input_ref), output_ref = COALESCE(?, output_ref) "
                    "WHERE span_id = ?",
                    (_now(), status, json.dumps(merged, ensure_ascii=False, default=str),
                     input_ref, output_ref, span_id))
        except Exception:  # noqa: BLE001
            return

    def close_running(self, status: str = "interrupted") -> int:
        """Close every span of the wave still `running` (process died, wave finalized).

        Args:
            status: Status assigned to abandoned spans.

        Returns:
            Number of spans closed.
        """
        try:
            with _connect(self.db_path) as conn:
                self._ensure(conn)
                cur = conn.execute(
                    "UPDATE ops_spans SET ended_at = ?, status = ? "
                    "WHERE trace_id = ? AND status = 'running' AND kind != 'workflow'",
                    (_now(), status, self.trace_id))
                return cur.rowcount
        except Exception:  # noqa: BLE001
            return 0

    def child_env(self, parent_id: str | None) -> dict[str, str]:
        """Build environment variables so a child process writes spans under `parent_id`.

        Args:
            parent_id: Parent span of the spans the child process will create.

        Returns:
            Dict of environment variables.
        """
        env = {ENV_DB: self.db_path, ENV_WAVE: self.trace_id}
        if parent_id:
            env[ENV_PARENT] = parent_id
        return env


class SpanHandle:
    """Handle of an open span, used in a `with` block.

    Attributes:
        id: Span identifier, None when tracing is off.
        status: Final status that will be recorded when the span closes.
    """

    def __init__(self, tracer: Tracer | None, span_id: str | None) -> None:
        """Bind the handle to an open span.

        Args:
            tracer: Tracer that owns the span.
            span_id: Span identifier.
        """
        self._tracer = tracer
        self.id = span_id
        self._attrs: dict[str, Any] = {}
        self.status = "ok"

    def set(self, **attrs: Any) -> None:
        """Record attributes that will be merged into the span when it closes.

        Args:
            **attrs: Attributes.
        """
        if "status" in attrs:  # `status` is a parameter of finish(); keep the value under another name
            attrs["result_status"] = attrs.pop("status")
        self._attrs.update(attrs)

    def fail(self, status: str = "fail", **attrs: Any) -> None:
        """Mark the span as ended unsuccessfully.

        Args:
            status: Final status.
            **attrs: Additional attributes.
        """
        self.status = status
        self._attrs.update(attrs)

    def env(self) -> dict[str, str]:
        """Return the environment variables for the child process of this span.

        Returns:
            Dict of environment variables, empty when tracing is off.
        """
        return self._tracer.child_env(self.id) if self._tracer and self.id else {}


def from_env() -> Tracer | None:
    """Build a tracer from the environment variables set by the daemon; None on manual runs.

    Returns:
        A Tracer whose default parent is `OPS_TRACE_PARENT`, or None.
    """
    db, wave = os.environ.get(ENV_DB), os.environ.get(ENV_WAVE)
    if not db or not wave:
        return None
    return Tracer(db, wave, os.environ.get(ENV_PARENT) or None)


@contextmanager
def span(name: str, kind: str, actor_id: str | None = None, *, tracer: Tracer | None = None,
         span_id: str | None = None, **attrs: Any) -> Iterator[SpanHandle]:
    """Open a span around a block; an exception marks it `fail` and is re-raised.

    Does nothing (empty handle) when there is no tracer and no environment variables.

    Args:
        name: Span name.
        kind: Span kind.
        actor_id: Agent identifier in the registry.
        tracer: Explicit tracer; when omitted one is built from the environment.
        span_id: Fixed span identifier.
        **attrs: Initial attributes.

    Yields:
        The SpanHandle.
    """
    tr = tracer or from_env()
    sid = tr.begin(name, kind, actor_id, span_id=span_id, **attrs) if tr else None
    handle = SpanHandle(tr, sid)
    try:
        yield handle
    except BaseException:
        handle.status = "fail" if handle.status == "ok" else handle.status
        raise
    finally:
        if tr and sid:
            tr.finish(sid, handle.status, **handle._attrs)
