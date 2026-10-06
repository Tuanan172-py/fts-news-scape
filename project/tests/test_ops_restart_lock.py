"""Kiểm thử khoá một thể hiện của daemon chờ ân hạn khi khởi động lại."""

from __future__ import annotations

import subprocess
import sys
import textwrap
import time
from pathlib import Path

from src.ops.daemon import acquire_single_instance

PROJECT_ROOT = Path(__file__).resolve().parent.parent

HOLDER = textwrap.dedent("""
    import sys, time
    sys.path.insert(0, {root!r})
    from src.core.proclock import SingleInstanceLock
    lock = SingleInstanceLock({path!r})
    assert lock.acquire()
    print("held", flush=True)
    time.sleep({hold})
""")


def _hold(path: Path, hold: float) -> subprocess.Popen:
    code = HOLDER.format(root=str(PROJECT_ROOT), path=str(path), hold=hold)
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "held"
    return proc


def test_restart_waits_for_dying_holder(tmp_path):
    """Tiến trình cũ nhả khoá sau 2 s thì daemon mới chiếm được trong ân hạn."""
    path = tmp_path / "ops_daemon.lock"
    proc = _hold(path, 2)
    try:
        lock = acquire_single_instance(path, grace_s=20, poll_s=0.5)
        assert lock is not None
        lock.release()
    finally:
        proc.kill()


def test_live_holder_still_wins_after_grace(tmp_path):
    """Daemon thật đang chạy thì bản mới thoát sau ân hạn, không chạy trùng."""
    path = tmp_path / "ops_daemon.lock"
    proc = _hold(path, 60)
    try:
        t0 = time.monotonic()
        assert acquire_single_instance(path, grace_s=1.5, poll_s=0.5) is None
        assert time.monotonic() - t0 >= 1.4
    finally:
        proc.kill()
