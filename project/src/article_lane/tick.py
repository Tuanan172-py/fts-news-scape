"""Trigger article analysis waves automatically based on schedule windows and the pending-article threshold."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


from src.agent.article_contract import analyzed_l1_sql
from src.core import paths
from src.core.stdio import force_utf8_stdio
from src.db.preflight import resolve_db_path
from src.core.paths import PROJECT_ROOT
from src.db.connect import open_ro

force_utf8_stdio()

SCRIPTS_DIR = PROJECT_ROOT / "scripts"
PYTHON_EXE = sys.executable

DATA_DIR = paths.data_root()
KILL_SWITCH_PATH = DATA_DIR / "AGY_STOP"
LOCK_FILE_PATH = DATA_DIR / ".pipeline.lock"
STANDING_ORDER_PATH = DATA_DIR / "agy_standing_order.yaml"

DEFAULT_PENDING_THRESHOLD = 50
DEFAULT_WAVE_LIMIT = 100
DEFAULT_BATCH_SIZE = 50


def check_kill_switch() -> bool:
    """Check whether the emergency stop flag file exists.

    Returns:
        True if the AGY_STOP file exists, otherwise False.
    """
    if KILL_SWITCH_PATH.exists():
        print(f"🛑 Phát hiện cờ dừng khẩn cấp tại {KILL_SWITCH_PATH}. Bỏ qua chu kỳ xử lý.")
        return True
    return False


def is_process_running(pid: int) -> bool:
    """Check whether a process with the given PID is running on the operating system.

    Args:
        pid: Process identifier.

    Returns:
        True if the process is running, otherwise False.
    """
    if pid <= 0:
        return False
    try:
        import psutil

        return psutil.pid_exists(pid)
    except ImportError:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, SystemError):
            return False


class PipelineLock:
    """Manage a single-process lock that prevents concurrent wave runs.

    Attributes:
        lock_path: Path of the lock file on local disk.
        locked: Whether this instance currently holds the lock.
    """

    def __init__(self, lock_path: Path = LOCK_FILE_PATH):
        """Initialize the lock.

        Args:
            lock_path: Path of the process lock file.
        """
        self.lock_path = lock_path
        self.locked = False

    def acquire(self) -> bool:
        """Try to take ownership of the process lock.

        Returns:
            True if the lock was acquired, False if another process holds it.
        """
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists():
            try:
                content = self.lock_path.read_text(encoding="utf-8").strip()
                data = json.loads(content)
                pid = data.get("pid", 0)
                if pid and is_process_running(pid):
                    print(f"🔒 Đợt khác đang chạy (PID={pid}). Bỏ qua chu kỳ này.")
                    return False
                print(f"⚠️ Phát hiện khóa cũ không còn tiến trình sống (PID={pid}). Tiến hành thu hồi.")
            except Exception:
                pass

        payload = {
            "pid": os.getpid(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "script": "article_tick.py",
        }
        try:
            self.lock_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            self.locked = True
            return True
        except Exception as exc:
            print(f"❌ Không thể tạo tệp khóa {self.lock_path}: {exc}")
            return False

    def release(self) -> None:
        """Release the process lock when the run completes."""
        if self.locked and self.lock_path.exists():
            try:
                self.lock_path.unlink(missing_ok=True)
                self.locked = False
            except Exception as exc:
                print(f"⚠️ Lỗi giải phóng tệp khóa: {exc}")

    def __enter__(self):
        """Enter the context manager.

        Returns:
            This lock instance.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Release the lock on context exit.

        Args:
            exc_type: Exception type raised in the block, if any.
            exc_val: Exception instance raised in the block, if any.
            exc_tb: Traceback of the exception, if any.
        """
        self.release()


def assert_db_path() -> Path:
    """Verify that the production database path is valid and outside OneDrive.

    Returns:
        The resolved database file path.

    Raises:
        RuntimeError: If the database path is inside OneDrive or SharePoint.
    """
    db_path = resolve_db_path()
    path_str = str(db_path).lower()
    if "onedrive" in path_str or "sharepoint" in path_str:
        raise RuntimeError(f"Cơ sở dữ liệu {db_path} nằm trong OneDrive/SharePoint, vi phạm Rule 03.")
    return db_path


def count_pending_articles(db_path: Path) -> int:
    """Count silver-tier articles that have no accepted model analysis yet.

    Args:
        db_path: Path of the monocle.db database file.

    Returns:
        Number of articles waiting for processing.
    """
    if not db_path.exists():
        return 0

    sql = (
        "SELECT count(DISTINCT a.url_title_hash) "
        "FROM articles a "
        "JOIN work_items w ON w.article_id = a.url_title_hash "
        "WHERE w.package_path IS NOT NULL "
        "  AND NOT EXISTS ("
        "      SELECT 1 FROM l1_outputs o "
        "      WHERE o.article_id = a.url_title_hash "
        f"        AND {analyzed_l1_sql('o')}"
        "  )"
    )

    conn = open_ro(db_path)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        row = cur.fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def is_flush_window(dt: datetime | None = None) -> tuple[bool, str]:
    """Check whether a time falls inside a market flush window.

    Flush windows (Vietnam time):
    - 07:15 - 07:45 (pre-market)
    - 12:15 - 12:45 (lunch break)
    - 15:15 - 15:45 (after the ATC closing auction)
    - 17:15 - 17:45 (end-of-day financial report releases)

    Args:
        dt: Time to check. Defaults to the current time.

    Returns:
        `(True, window_name)` when inside a window, otherwise `(False, "")`.
    """
    now = dt or datetime.now()
    minutes = now.hour * 60 + now.minute

    windows = [
        (7 * 60 + 15, 7 * 60 + 45, "pre_market_0730"),
        (12 * 60 + 15, 12 * 60 + 45, "midday_1230"),
        (15 * 60 + 15, 15 * 60 + 45, "post_market_1530"),
        (17 * 60 + 15, 17 * 60 + 45, "eod_1730"),
    ]

    for start_m, end_m, name in windows:
        if start_m <= minutes <= end_m:
            return True, name
    return False, ""


def evaluate_trigger(
    n_pending: int,
    *,
    threshold: int = DEFAULT_PENDING_THRESHOLD,
    force: bool = False,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Evaluate whether a new article wave should be triggered.

    Args:
        n_pending: Number of articles waiting for analysis.
        threshold: Minimum accumulated volume that triggers a wave.
        force: Trigger regardless of the conditions.
        now: Time of evaluation.

    Returns:
        `(True, trigger_reason)` when a wave should run, otherwise `(False, skip_reason)`.
    """
    if force:
        return True, "forced"

    if n_pending <= 0:
        return False, "Không có bài viết nào đang chờ xử lý."

    if n_pending >= threshold:
        return True, f"Ngưỡng tích lũy vượt mức ({n_pending} >= {threshold} bài)."

    in_flush, flush_name = is_flush_window(now)
    if in_flush and n_pending > 0:
        return True, f"Khung giờ gom vét thị trường ({flush_name}, {n_pending} bài tồn đọng)."

    return False, f"Chưa đủ ngưỡng ({n_pending}/{threshold} bài) và ngoài khung giờ gom vét."


def load_standing_order() -> dict[str, Any]:
    """Load the time-limited standing order file if present.

    Returns:
        Standing order data as a dict.
    """
    if not STANDING_ORDER_PATH.exists():
        # Default to level L1 when the file is not configured.
        return {
            "level": "L1",
            "model": "gemini-3.8-flash-low",
            "valid_until": "2099-12-31",
            "max_limit": 100,
        }

    try:
        lines = STANDING_ORDER_PATH.read_text(encoding="utf-8").splitlines()
        data: dict[str, Any] = {}
        for line in lines:
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue
            if ":" in line_str:
                k, v = line_str.split(":", 1)
                data[k.strip()] = v.strip().strip("'\"")
        return data
    except Exception as exc:
        print(f"⚠️ Lỗi đọc standing order: {exc}. Dùng mức L1 mặc định.")
        return {"level": "L1", "model": "gemini-3.8-flash-low"}


def run_tick(args: argparse.Namespace) -> int:
    """Run one check cycle and trigger a wave when the conditions are met.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 on success, non-zero on error).
    """
    if check_kill_switch():
        return 0

    try:
        db_path = assert_db_path()
    except Exception as exc:
        print(f"❌ Lỗi kiểm tra CSDL: {exc}")
        return 1

    locker = PipelineLock()
    if not locker.acquire():
        return 0

    try:
        n_pending = count_pending_articles(db_path)
        standing = load_standing_order()
        level = args.level or standing.get("level", "L1").upper()
        threshold = args.threshold or DEFAULT_PENDING_THRESHOLD
        limit = min(args.limit or DEFAULT_WAVE_LIMIT, int(standing.get("max_limit", 100)))

        should_run, reason = evaluate_trigger(
            n_pending, threshold=threshold, force=args.force
        )

        print("=" * 80)
        print(f" 🛰️  ARTICLE TICK — {datetime.now():%Y-%m-%d %H:%M:%S}")
        print("=" * 80)
        print(f"CSDL       : {db_path}")
        print(f"Chờ xử lý  : {n_pending} bài viết")
        print(f"Cấp tự chủ : {level}")
        print(f"Đánh giá   : {'KÍCH HOẠT ĐỢT' if should_run else 'BỎ QUA'}")
        print(f"Lý do      : {reason}")
        print("=" * 80)

        if not should_run or args.dry_run:
            return 0

        # Start the wave.
        wave_id = f"W{datetime.now():%m%d%H%M}"
        run_script = SCRIPTS_DIR / "article_run.py"

        # Step 1: prepare and analyze through agy.
        prep_cmd = [
            PYTHON_EXE,
            str(run_script),
            "--wave",
            wave_id,
            "--runner",
            "agy",
            "--batch",
            str(args.batch or DEFAULT_BATCH_SIZE),
            "--limit",
            str(limit),
            "--analyze",
        ]
        print(f"\n▶ Khởi động đợt {wave_id} qua agy runner (limit={limit}, batch={args.batch or DEFAULT_BATCH_SIZE})...")
        res_prep = subprocess.run(prep_cmd, cwd=str(PROJECT_ROOT))
        if res_prep.returncode != 0:
            print(f"❌ Đợt {wave_id} thất bại tại khâu phân tích agy (code={res_prep.returncode}).")
            return res_prep.returncode

        # Step 2: finish and load into the database (autonomy level L2 or --finish flag).
        if level >= "L2" or args.finish:
            print(f"\n▶ Cấp tự chủ {level}: Tự động hoàn tất và nạp CSDL...")
            fin_cmd = [
                PYTHON_EXE,
                str(run_script),
                "--wave",
                wave_id,
                "--runner",
                "agy",
                "--finish",
            ]
            res_fin = subprocess.run(fin_cmd, cwd=str(PROJECT_ROOT))
            if res_fin.returncode != 0:
                print(f"❌ Đợt {wave_id} thất bại tại khâu nạp CSDL (code={res_fin.returncode}).")
                return res_fin.returncode
            print(f"\n✅ ĐỢT {wave_id} ĐÃ HOÀN TẤT VÀ NẠP CSDL THÀNH CÔNG.")
        else:
            print(f"\nⓘ Cấp tự chủ {level}: Đợt {wave_id} đã phân tích xong trên đĩa. "
                  f"Dừng trước bước nạp CSDL. Chạy `--finish` khi sẵn sàng:")
            print(f"   python scripts/article_run.py --wave {wave_id} --runner agy --finish")

        return 0

    finally:
        locker.release()


def main(argv: list[str] | None = None) -> int:
    """Run the article_tick command line.

    Args:
        argv: Command-line arguments. Defaults to `sys.argv`.

    Returns:
        Process exit code.
    """
    ap = argparse.ArgumentParser(description="Bộ điều phối tự động kích hoạt Article Lane qua agy")
    ap.add_argument("--tick", action="store_true", help="Chạy một chu kỳ kiểm tra và thực thi")
    ap.add_argument("--status", action="store_true", help="Chỉ kiểm tra và in trạng thái backlog rồi thoát")
    ap.add_argument("--force", action="store_true", help="Ép buộc kích hoạt đợt bỏ qua điều kiện ngưỡng")
    ap.add_argument("--dry-run", action="store_true", help="Đánh giá điều kiện nhưng không thực thi")
    ap.add_argument("--threshold", type=int, default=DEFAULT_PENDING_THRESHOLD, help="Ngưỡng bài chờ tối thiểu")
    ap.add_argument("--limit", type=int, default=DEFAULT_WAVE_LIMIT, help="Số bài tối đa mỗi đợt")
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH_SIZE, help="Cỡ lô bài viết")
    ap.add_argument("--level", choices=["L0", "L1", "L2"], help="Ghi đè cấp độ tự chủ")
    ap.add_argument("--finish", action="store_true", help="Tự động chạy --finish sau khi phân tích")
    args = ap.parse_args(argv)

    if args.status:
        try:
            db_path = assert_db_path()
            n_pending = count_pending_articles(db_path)
            in_flush, flush_name = is_flush_window()
            print("=" * 70)
            print(" 🛰️  ARTICLE TICK STATUS")
            print("=" * 70)
            print(f"CSDL          : {db_path}")
            print(f"Bài đang chờ  : {n_pending} bài")
            print(f"Khung giờ gom : {'CÓ (' + flush_name + ')' if in_flush else 'Không'}")
            print(f"Khóa tiến trình: {'Đang khóa' if LOCK_FILE_PATH.exists() else 'Sẵn sàng'}")
            print(f"Kill-Switch   : {'BẬT (AGY_STOP tồn tại)' if KILL_SWITCH_PATH.exists() else 'Tắt'}")
            print("=" * 70)
            return 0
        except Exception as exc:
            print(f"❌ Lỗi: {exc}")
            return 1

    return run_tick(args)

