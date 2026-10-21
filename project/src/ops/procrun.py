"""Run a step as a child process with a deadline, progress tracking and whole-tree kill."""

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
    """Create once a Job Object that kills every child process when the daemon dies.

    The job handle lives only in the daemon process. When the daemon exits or is killed,
    Windows closes the handle and the KILL_ON_JOB_CLOSE flag kills the whole
    `article_run` → `agy` tree. Without this mechanism, a half-finished batch keeps
    spending tokens after the daemon dies, and the recovery then re-runs the same batch.

    Returns:
        The job handle, or None when not on Windows or when creation fails.
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
    """Start a child process that is already inside the daemon Job Object.

    The process is created suspended, attached to the job, and only then resumed. This
    order is required: the venv `python.exe` is a launcher that attaches itself to its own
    job with the SILENT_BREAKAWAY_OK flag. Attaching the daemon job after the launcher makes
    the daemon job a child of the launcher job, and the real interpreter spawned by the
    launcher escapes both. Attaching first nests the launcher job inside the daemon job, and
    every descendant still belongs to the daemon job.

    Args:
        cmd: Command and arguments.
        **kwargs: Arguments passed to `subprocess.Popen`.

    Returns:
        Pair (process, whether it was attached to the job).
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
    """Result of running one step.

    Attributes:
        returncode: Exit code; -1 when killed.
        outcome: `ok`, `failed`, `timeout`, `stalled` or `cancelled`.
        duration_s: Duration in seconds.
        tail: Last lines of the step log.
        log_path: Path of the step log.
    """

    returncode: int
    outcome: str
    duration_s: float
    tail: str
    log_path: Path

    @property
    def ok(self) -> bool:
        """Report whether the step exited with code 0."""
        return self.outcome == "ok"


def kill_tree(pid: int) -> None:
    """Kill a process together with all its descendants.

    Args:
        pid: Root process identifier.
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
    """Read the last lines of a log file, only from `start_offset` onward.

    Args:
        path: File path.
        lines: Number of lines.
        start_offset: Byte offset where the current run starts in the appended file.

    Returns:
        Text of the last lines, empty when the file cannot be read.
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
    """Run a command, write stdout/stderr to a log, and monitor the deadline, progress and stop signal.

    Progress counts as made when the value returned by `progress_fn` changes. If it stays
    unchanged for `silence_s` seconds, the step is considered hung and is killed.

    Args:
        cmd: Command and arguments.
        cwd: Working directory.
        log_path: Log file (appended).
        deadline_s: Maximum run time.
        progress_fn: Progress measuring function, called every cycle.
        silence_s: Maximum silent time.
        stop_fn: Function that returns True when the step must be cancelled.
        poll_s: Polling interval.
        extra_env: Extra environment variables for the child process (tracing context).

    Returns:
        The StepResult.
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
        # The log is appended across reruns; batch results are read only from this run,
        # otherwise a FATAL line from a previous run would be counted again by the breaker.
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
    """Build the command that calls a Python script with the running interpreter.

    Args:
        script: Script path.
        *args: Script arguments.

    Returns:
        Command argument list.
    """
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        exe = exe[: -len("pythonw.exe")] + "python.exe"
    return [exe, str(script), *args]
