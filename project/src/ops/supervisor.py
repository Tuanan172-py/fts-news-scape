"""Giữ tiến trình cào tin `morninger` luôn sống, khởi động lại có trần."""

from __future__ import annotations

import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from typing import Callable

from src.ops.config import PROJECT_ROOT
from src.ops.present import alert_card
from src.ops.procrun import CREATE_NO_WINDOW
from src.ops.store import OpsStore


def _capture_lock_held(lock_path: Path) -> bool:
    from src.core.proclock import SingleInstanceLock

    lock = SingleInstanceLock(lock_path)
    if lock.acquire():
        lock.release()
        return False
    return True


class CaptureSupervisor:
    """Giám sát `python -m src.morninger` theo kiểu cây giám sát một nhánh.

    Tiến trình cào đã chạy sẵn bên ngoài (giữ `capture.lock`) thì chỉ theo dõi, không
    sinh thêm. Tiến trình chết thì khởi động lại với backoff; quá `max_restarts` trong
    `restart_window_minutes` thì dừng và gửi cảnh báo đỏ.

    Attributes:
        store: Store vận hành.
        cfg: Mục `supervisor` của cấu hình.
        lock_path: Tệp `capture.lock`.
        log_path: Nhật ký stdout/stderr của tiến trình con.
    """

    def __init__(self, store: OpsStore, cfg: dict, lock_path: Path, log_path: Path, *,
                 spawn: Callable[[], subprocess.Popen] | None = None,
                 lock_held: Callable[[Path], bool] = _capture_lock_held,
                 clock: Callable[[], float] = time.monotonic) -> None:
        """Gắn phụ thuộc.

        Args:
            store: Store vận hành.
            cfg: Mục `supervisor` của cấu hình.
            lock_path: Tệp `capture.lock`.
            log_path: Nhật ký tiến trình con.
            spawn: Hàm sinh tiến trình, thay được trong kiểm thử.
            lock_held: Hàm kiểm khoá cào đang bị giữ.
            clock: Đồng hồ đơn điệu.
        """
        self.store = store
        self.cfg = cfg
        self.lock_path = lock_path
        self.log_path = log_path
        self._spawn = spawn or self._default_spawn
        self._lock_held = lock_held
        self._clock = clock
        self.proc: subprocess.Popen | None = None
        self.mode = "unknown"
        self.restarts: deque[float] = deque()
        self.next_start_at = 0.0
        self.gave_up = False

    def _default_spawn(self) -> subprocess.Popen:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        exe = sys.executable
        if exe.lower().endswith("pythonw.exe"):
            exe = exe[: -len("pythonw.exe")] + "python.exe"
        log = open(self.log_path, "a", encoding="utf-8")
        return subprocess.Popen([exe, "-m", "src.morninger"], cwd=str(PROJECT_ROOT),
                                stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)

    def reset(self) -> None:
        """Xoá trạng thái bỏ cuộc để thử khởi động lại theo lệnh người vận hành."""
        self.gave_up = False
        self.restarts.clear()
        self.next_start_at = 0.0

    def tick(self) -> str:
        """Kiểm một lần và khởi động lại nếu cần.

        Returns:
            Chế độ hiện tại: `disabled`, `external`, `child`, `backoff`, `gave_up`.
        """
        if not self.cfg.get("manage_capture", True):
            self.mode = "disabled"
            return self.mode
        if self.proc is not None:
            rc = self.proc.poll()
            if rc is None:
                self.mode = "child"
                return self.mode
            self.store.emit("capture.exited", f"morninger thoát với mã {rc}", level="error",
                            actor="daemon", data={"rc": rc})
            self.proc = None
            self.next_start_at = self._clock() + self._backoff()
        if self.gave_up:
            self.mode = "gave_up"
            return self.mode
        if self._lock_held(self.lock_path):
            if self.mode != "external":
                self.store.emit("capture.external", "Tiến trình cào bên ngoài đang giữ "
                                "capture.lock: chỉ theo dõi, không sinh thêm.", actor="daemon")
            self.mode = "external"
            return self.mode
        now = self._clock()
        if now < self.next_start_at:
            self.mode = "backoff"
            return self.mode
        window = float(self.cfg.get("restart_window_minutes", 30)) * 60
        while self.restarts and now - self.restarts[0] > window:
            self.restarts.popleft()
        if len(self.restarts) >= int(self.cfg.get("max_restarts", 5)):
            self.gave_up = True
            self.mode = "gave_up"
            msg = (f"morninger chết {len(self.restarts)} lần trong "
                   f"{window / 60:.0f} phút: ngừng khởi động lại. Xem ops_logs/capture.log.")
            self.store.emit("capture.gave_up", msg, level="critical", actor="daemon")
            self.store.alert("critical", alert_card(
                "critical", f"Cào tin dừng: morninger chết {len(self.restarts)} lần trong "
                f"{window / 60:.0f} phút", "bài mới không được thu thập",
                "kiểm ops_logs/capture.log rồi bấm Thử lại", "/log 15"),
                dedup_key="capture:gave_up", buttons=[[("Thử lại", "/capture restart")]])
            return self.mode
        self.proc = self._spawn()
        self.restarts.append(now)
        self.mode = "child"
        self.store.emit("capture.started", f"Khởi động morninger (pid {self.proc.pid}).",
                        actor="daemon", data={"pid": self.proc.pid})
        return self.mode

    def _backoff(self) -> float:
        steps = self.cfg.get("restart_backoff_seconds") or [10]
        return float(steps[min(len(self.restarts), len(steps)) - 1 if self.restarts else 0])
