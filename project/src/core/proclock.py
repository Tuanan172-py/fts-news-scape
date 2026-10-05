"""Tiện ích khóa cố vấn (advisory lock) cho tiến trình lập lịch scheduler."""

from __future__ import annotations

import os
import socket

SCHEDULER_LOCK_STALE_SECONDS = 2400  # 40 phút


def lock_owner() -> str:
    """Tạo định danh duy nhất cho tiến trình sở hữu khóa dạng hostname:pid.

    Returns:
        Chuỗi định danh tiến trình hiện tại.
    """
    return f"{socket.gethostname()}:{os.getpid()}"


CAPTURE_LOCK_NAME = "capture.lock"
# Khoá một byte ở xa phần nội dung để tiến trình khác vẫn đọc được định danh chủ khoá.
_LOCK_OFFSET = 1 << 20


class SingleInstanceLock:
    """Khoá tệp độc quyền giữ suốt đời tiến trình, hệ điều hành tự nhả khi tiến trình chết.

    Khoá cố vấn trong `pipeline_state` phụ thuộc nhịp tim và ngưỡng cũ, nên hai tiến
    trình cào vẫn có thể cùng chạy. Khoá tệp này không có trạng thái cũ: tiến trình giữ
    khoá còn sống thì tiến trình khác không chiếm được, tiến trình chết thì khoá tự mất.

    Attributes:
        path: Đường dẫn tệp khoá, đặt trên đĩa cục bộ cạnh DB vận hành.
    """

    def __init__(self, path: str | os.PathLike) -> None:
        """Ghi nhận đường dẫn tệp khoá, chưa mở tệp.

        Args:
            path: Đường dẫn tệp khoá.
        """
        self.path = os.fspath(path)
        self._fh = None

    def acquire(self) -> bool:
        """Chiếm khoá không chờ.

        Returns:
            True khi chiếm được, False khi tiến trình khác đang giữ.
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
        """Đọc định danh tiến trình ghi trong tệp khoá.

        Returns:
            Chuỗi `hostname:pid`, rỗng khi không đọc được.
        """
        try:
            with open(self.path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""

    def release(self) -> None:
        """Nhả khoá nếu đang giữ; gọi lại nhiều lần không lỗi."""
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
    """Tạo khoá dùng chung cho mọi tiến trình cào tin (morninger, run_once, orchestrator).

    Tệp khoá nằm cạnh DB vận hành, ngoài OneDrive, nên mọi tiến trình trên cùng máy
    trỏ vào cùng một tệp.

    Returns:
        Đối tượng khoá chưa chiếm.
    """
    from src.core.config import resolve_db_path
    return SingleInstanceLock(resolve_db_path().parent / CAPTURE_LOCK_NAME)
