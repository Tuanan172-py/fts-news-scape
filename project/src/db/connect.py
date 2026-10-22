"""Open SQLite connections; the only module outside src/db internals that calls `sqlite3.connect` (ADR-0027.D4)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_TIMEOUT = 5.0


def open_ro(path: str | Path, *, timeout: float = DEFAULT_TIMEOUT, row_factory: bool = False) -> sqlite3.Connection:
    """Open a read-only connection that never creates the file and never takes a write lock.

    Args:
        path: Database file.
        timeout: Seconds to wait on a locked database.
        row_factory: Set `sqlite3.Row` as the row factory.

    Returns:
        Connection opened with `mode=ro`.
    """
    conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True, timeout=timeout)
    if row_factory:
        conn.row_factory = sqlite3.Row
    return conn


def open_rw(path: str | Path, *, timeout: float = DEFAULT_TIMEOUT, row_factory: bool = False,
            busy_timeout_ms: int | None = None) -> sqlite3.Connection:
    """Open a read-write connection, creating the file when it does not exist.

    Args:
        path: Database file.
        timeout: Seconds to wait on a locked database.
        row_factory: Set `sqlite3.Row` as the row factory.
        busy_timeout_ms: Value for `PRAGMA busy_timeout`; None leaves the default.

    Returns:
        Read-write connection.
    """
    conn = sqlite3.connect(str(path), timeout=timeout)
    if row_factory:
        conn.row_factory = sqlite3.Row
    if busy_timeout_ms is not None:
        conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
    return conn
