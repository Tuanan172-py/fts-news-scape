"""Chạy một bước dưới dạng tiến trình con có deadline, đo tiến độ và kill cả cây."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

CREATE_NO_WINDOW = 0x08000000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_CREATE_SUSPENDED = 0x00000004

_job_handle: int | None = None


def _daemon_job() -> int | None:
    """Tạo (một lần) Job Object tự kill mọi tiến trình con khi daemon chết.

    Handle của job chỉ nằm trong tiến trình daemon. Daemon thoát hoặc bị kill thì
    Windows đóng handle, và cờ KILL_ON_JOB_CLOSE kill trọn cây `article_run` → `agy`.
    Không có cơ chế này, lô đang chạy dở vẫn tiêu token sau khi daemon chết, rồi
    lần khôi phục chạy lại đúng lô ấy lần nữa.

    Returns:
        Handle của job, hoặc None khi không phải Windows hoặc tạo thất bại.
    """
    global _job_handle
    if os.name != "nt":
        return None
    if _job_handle is not None:
        return _job_handle
    import ctypes
    from ctypes import wintypes

    class _BasicLimit(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _ExtendedLimit(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _BasicLimit),
                    ("IoInfo", _IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                            wintypes.DWORD]
    job = k32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = _ExtendedLimit()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k32.SetInformationJobObject(job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                       ctypes.byref(info), ctypes.sizeof(info)):
        k32.CloseHandle(job)
        return None
    _job_handle = job
    return job


def popen_in_daemon_job(cmd: list[str], **kwargs) -> tuple[subprocess.Popen, bool]:
    """Khởi chạy tiến trình con đã nằm sẵn trong Job Object của daemon.

    Tiến trình được tạo ở trạng thái treo, gắn vào job, rồi mới chạy. Thứ tự này bắt
    buộc: `python.exe` của venv là một launcher tự gắn mình vào job riêng có cờ
    SILENT_BREAKAWAY_OK. Gắn job của daemon sau launcher thì job của daemon thành job
    con của launcher, và trình thông dịch thật do launcher sinh ra thoát khỏi cả hai.
    Gắn trước thì job của launcher lồng bên trong job của daemon, và mọi hậu duệ vẫn
    thuộc job của daemon.

    Args:
        cmd: Lệnh và tham số.
        **kwargs: Tham số chuyển cho `subprocess.Popen`.

    Returns:
        Cặp (tiến trình, đã gắn được vào job hay chưa).
    """
    job = _daemon_job()
    if job is None:
        return subprocess.Popen(cmd, **kwargs), False
    import ctypes
    from ctypes import wintypes

    flags = int(kwargs.pop("creationflags", 0)) | _CREATE_SUSPENDED
    proc = subprocess.Popen(cmd, creationflags=flags, **kwargs)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    handle = wintypes.HANDLE(int(proc._handle))  # type: ignore[attr-defined]
    try:
        attached = bool(k32.AssignProcessToJobObject(job, handle))
    finally:
        ntdll.NtResumeProcess(handle)
    return proc, attached


@dataclass
class StepResult:
    """Kết quả chạy một bước.

    Attributes:
        returncode: Mã thoát; -1 khi bị kill.
        outcome: `ok`, `failed`, `timeout`, `stalled` hoặc `cancelled`.
        duration_s: Thời lượng tính bằng giây.
        tail: Các dòng cuối của nhật ký bước.
        log_path: Đường dẫn nhật ký bước.
    """

    returncode: int
    outcome: str
    duration_s: float
    tail: str
    log_path: Path

    @property
    def ok(self) -> bool:
        """True khi bước thoát 0."""
        return self.outcome == "ok"


def kill_tree(pid: int) -> None:
    """Kill một tiến trình cùng mọi tiến trình con cháu.

    Args:
        pid: Mã tiến trình gốc.
    """
    try:
        import psutil
    except ImportError:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True, check=False)
        return
    try:
        root = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    procs = root.children(recursive=True) + [root]
    for p in procs:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(procs, timeout=10)


def read_tail(path: Path, lines: int = 40, *, start_offset: int = 0) -> str:
    """Đọc các dòng cuối của một tệp nhật ký, chỉ trong phần từ `start_offset` trở đi.

    Args:
        path: Đường dẫn tệp.
        lines: Số dòng.
        start_offset: Vị trí byte bắt đầu của lần chạy hiện tại trong tệp ghi nối.

    Returns:
        Văn bản các dòng cuối, rỗng khi không đọc được.
    """
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(start_offset, size - 64_000))
            data = f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(data.splitlines()[-lines:])


def run_step(cmd: list[str], *, cwd: Path, log_path: Path, deadline_s: float,
             progress_fn: Callable[[], object] | None = None,
             silence_s: float | None = None,
             stop_fn: Callable[[], bool] | None = None,
             poll_s: float = 2.0, extra_env: dict[str, str] | None = None) -> StepResult:
    """Chạy lệnh, ghi stdout/stderr vào nhật ký và giám sát deadline, tiến độ, lệnh dừng.

    Tiến độ được coi là có khi giá trị trả về của `progress_fn` thay đổi. Hết
    `silence_s` giây không đổi thì bước bị coi là treo và bị kill.

    Args:
        cmd: Lệnh và tham số.
        cwd: Thư mục làm việc.
        log_path: Tệp nhật ký (ghi nối).
        deadline_s: Trần thời gian chạy.
        progress_fn: Hàm đo tiến độ, gọi mỗi chu kỳ.
        silence_s: Thời gian im lặng tối đa.
        stop_fn: Hàm trả True khi cần huỷ bước.
        poll_s: Chu kỳ kiểm tra.
        extra_env: Biến môi trường thêm cho tiến trình con (ngữ cảnh ghi vết).

    Returns:
        StepResult.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(extra_env or {})
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    start = time.monotonic()
    flags = CREATE_NO_WINDOW if os.name == "nt" else 0
    with open(log_path, "a", encoding="utf-8") as log:
        log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} $ {' '.join(cmd)}\n")
        log.flush()
        # Nhật ký ghi nối qua các lần chạy lại; kết quả lô chỉ được đọc từ lần chạy này,
        # nếu không dòng FATAL của lần trước bị đếm lại vào breaker.
        run_offset = log.buffer.tell() if hasattr(log, "buffer") else log.tell()
        proc, attached = popen_in_daemon_job(cmd, cwd=str(cwd), stdout=log,
                                             stderr=subprocess.STDOUT,
                                             stdin=subprocess.DEVNULL, env=env,
                                             creationflags=flags)
        if os.name == "nt" and not attached:
            log.write("===== cảnh báo: không gắn được Job Object; tiến trình con có thể "
                      "sống sót nếu daemon chết\n")
            log.flush()
        last_progress = progress_fn() if progress_fn else None
        last_change = start
        outcome = None
        while True:
            rc = proc.poll()
            if rc is not None:
                outcome = "ok" if rc == 0 else "failed"
                break
            now = time.monotonic()
            if stop_fn and stop_fn():
                outcome = "cancelled"
            elif now - start > deadline_s:
                outcome = "timeout"
            elif progress_fn:
                cur = progress_fn()
                if cur != last_progress:
                    last_progress, last_change = cur, now
                elif silence_s and now - last_change > silence_s:
                    outcome = "stalled"
            if outcome:
                kill_tree(proc.pid)
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass
                rc = -1
                log.write(f"\n===== bước bị dừng: {outcome}\n")
                break
            time.sleep(poll_s)
    return StepResult(returncode=rc if rc is not None else -1, outcome=outcome,
                      duration_s=time.monotonic() - start,
                      tail=read_tail(log_path, start_offset=run_offset),
                      log_path=log_path)


def python_cmd(script: Path, *args: str) -> list[str]:
    """Dựng lệnh gọi một script Python bằng chính interpreter đang chạy.

    Args:
        script: Đường dẫn script.
        *args: Tham số.

    Returns:
        Danh sách tham số lệnh.
    """
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        exe = exe[: -len("pythonw.exe")] + "python.exe"
    return [exe, str(script), *args]
