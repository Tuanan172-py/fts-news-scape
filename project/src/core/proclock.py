"""Provide advisory and single-instance locks for scheduler processes."""

from __future__ import annotations

import os
import socket

SCHEDULER_LOCK_STALE_SECONDS = 2400  # 40 minutes


def lock_owner() -> str:
    """Build a unique `hostname:pid` identity for the process that owns a lock.

    Returns:
        Identity string of the current process.
    """
    return f"{socket.gethostname()}:{os.getpid()}"


CAPTURE_LOCK_NAME = "capture.lock"
# Lock one byte far from the content so other processes can still read the lock owner identity.
_LOCK_OFFSET = 1 << 20


class SingleInstanceLock:
    """Hold an exclusive file lock for the lifetime of a process; the OS releases it when the process dies.

    The advisory lock in `pipeline_state` depends on a heartbeat and a staleness
    threshold, so two scrape processes can still run together. This file lock has no
    stale state: while the holder is alive no other process can take it, and when the
    holder dies the lock disappears.

    Attributes:
        path: Lock file path, placed on a local disk next to the operational DB.
    """

    def __init__(self, path: str | os.PathLike) -> None:
        """Record the lock file path without opening the file.

        Args:
            path: Lock file path.
        """
        self.path = os.fspath(path)
        self._fh = None

    def acquire(self) -> bool:
        """Take the lock without waiting.

        Returns:
            True if the lock was taken, False if another process holds it.
        """
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        fh = open(self.path, "a+", encoding="utf-8")
        try:
            fh.seek(_LOCK_OFFSET)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        fh.truncate(0)
        fh.write(lock_owner())
        fh.flush()
        self._fh = fh
        return True

    def holder(self) -> str:
        """Read the process identity written in the lock file.

        Returns:
            `hostname:pid` string, empty if it cannot be read.
        """
        try:
            with open(self.path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""

    def release(self) -> None:
        """Release the lock if held; repeated calls are safe."""
        if self._fh is None:
            return
        try:
            self._fh.seek(_LOCK_OFFSET)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self._fh.close()
            self._fh = None


def capture_lock() -> SingleInstanceLock:
    """Create the lock shared by every scraping process (morninger, run_once, orchestrator).

    The lock file sits next to the operational DB, outside OneDrive, so every process on
    the same machine points to the same file.

    Returns:
        A lock that is not yet taken.
    """
    from src.core.config import resolve_db_path
    return SingleInstanceLock(resolve_db_path().parent / CAPTURE_LOCK_NAME)
