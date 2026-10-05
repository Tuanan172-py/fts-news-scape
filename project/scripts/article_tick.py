"""Điều phối và tự động kích hoạt các đợt phân tích bài đăng theo lịch trình và ngưỡng bài chờ."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.stdio import force_utf8_stdio
from src.db.preflight import resolve_db_path

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
PYTHON_EXE = sys.executable

DATA_DIR = Path(os.environ.get("MONOCLE_DATA_DIR", r"C:\data\news-scape"))
KILL_SWITCH_PATH = DATA_DIR / "AGY_STOP"
LOCK_FILE_PATH = DATA_DIR / ".pipeline.lock"
STANDING_ORDER_PATH = DATA_DIR / "agy_standing_order.yaml"

DEFAULT_PENDING_THRESHOLD = 50
DEFAULT_WAVE_LIMIT = 100
DEFAULT_BATCH_SIZE = 50


def check_kill_switch() -> bool:
    """Kiểm tra sự tồn tại của tệp cờ dừng khẩn cấp.

    Returns:
        True nếu tệp AGY_STOP tồn tại, ngược lại False.
    """
    if KILL_SWITCH_PATH.exists():
        print(f"🛑 Phát hiện cờ dừng khẩn cấp tại {KILL_SWITCH_PATH}. Bỏ qua chu kỳ xử lý.")
        return True
    return False


def is_process_running(pid: int) -> bool:
    """Kiểm tra một tiến trình theo PID có đang hoạt động trên hệ điều hành hay không.

    Args:
        pid: Mã định danh tiến trình.

    Returns:
        True nếu tiến trình đang chạy, ngược lại False.
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
    """Quản lý khóa đơn tiến trình ngăn ngừa xung đột đợt chạy song song.

    Attributes:
        lock_path: Đường dẫn tệp khóa trên đĩa cục bộ.
        locked: Trạng thái hiện tại đã giữ khóa hay chưa.
    """

    def __init__(self, lock_path: Path = LOCK_FILE_PATH):
        """Khởi tạo đối tượng PipelineLock.

        Args:
            lock_path: Đường dẫn tệp khóa tiến trình.
        """
        self.lock_path = lock_path
        self.locked = False

    def acquire(self) -> bool:
        """Thử xác lập quyền sở hữu khóa tiến trình.

        Returns:
            True nếu chiếm khóa thành công, False nếu tiến trình khác đang giữ khóa.
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
        """Giải phóng khóa tiến trình sau khi hoàn tất."""
        if self.locked and self.lock_path.exists():
            try:
                self.lock_path.unlink(missing_ok=True)
                self.locked = False
            except Exception as exc:
                print(f"⚠️ Lỗi giải phóng tệp khóa: {exc}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


def assert_db_path() -> Path:
    """Xác nhận đường dẫn cơ sở dữ liệu sản xuất hợp lệ và nằm ngoài OneDrive.

    Returns:
        Đường dẫn tệp cơ sở dữ liệu đã phân giải.

    Raises:
        RuntimeError: Khi đường dẫn cơ sở dữ liệu không hợp lệ.
    """
    db_path = resolve_db_path()
    path_str = str(db_path).lower()
    if "onedrive" in path_str or "sharepoint" in path_str:
        raise RuntimeError(f"Cơ sở dữ liệu {db_path} nằm trong OneDrive/SharePoint, vi phạm Rule 03.")
    return db_path


def count_pending_articles(db_path: Path) -> int:
    """Đếm số bài viết tầng bạc chưa được mô hình phân tích đạt chuẩn.

    Args:
        db_path: Đường dẫn tệp cơ sở dữ liệu monocle.db.

    Returns:
        Số lượng bài viết đang chờ xử lý.
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
        "        AND o.dod_pass = 1 "
        "        AND COALESCE(o.l1_source, 'agent') <> 'code_first'"
        "  )"
    )

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        row = cur.fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def is_flush_window(dt: datetime | None = None) -> tuple[bool, str]:
    """Kiểm tra thời điểm hiện tại có thuộc khung giờ gom vét thị trường hay không.

    Các khung giờ gom vét (giờ Việt Nam):
    - 07:15 - 07:45 (Pre-market)
    - 12:15 - 12:45 (Nghỉ trưa)
    - 15:15 - 15:45 (Sau chốt ATC)
    - 17:15 - 17:45 (Công bố BCTC cuối ngày)

    Args:
        dt: Đối tượng thời gian cần kiểm tra (mặc định là giờ hiện tại).

    Returns:
        Cặp giá trị (True, tên_khung_giờ) nếu thỏa mãn, ngược lại (False, "").
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
    """Đánh giá điều kiện kích hoạt mở đợt xử lý bài đăng mới.

    Args:
        n_pending: Số lượng bài viết đang chờ phân tích.
        threshold: Ngưỡng tối thiểu kích hoạt theo khối lượng tích lũy.
        force: Cờ ép buộc kích hoạt bỏ qua điều kiện.
        now: Mốc thời gian đánh giá.

    Returns:
        Cặp giá trị (True, lý_do_kích_hoạt) nếu thỏa mãn, ngược lại (False, lý_do_bỏ_qua).
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
    """Nạp tệp chỉ lệnh ủy quyền vận hành có thời hạn nếu có.

    Returns:
        Từ điển dữ liệu chỉ lệnh vận hành.
    """
    if not STANDING_ORDER_PATH.exists():
        # Mặc định vận hành ở mức L1 nếu chưa cấu hình tệp
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
    """Thực thi một chu kỳ kiểm tra và kích hoạt đợt nếu thỏa mãn điều kiện.

    Args:
        args: Tham số dòng lệnh đã phân tích.

    Returns:
        Mã thoát tiến trình (0 thành công, khác 0 khi phát sinh lỗi).
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

        # Kích hoạt thực thi đợt
        wave_id = f"W{datetime.now():%m%d%H%M}"
        run_script = SCRIPTS_DIR / "article_run.py"

        # Bước 1: Chuẩn bị và phân tích qua agy
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

        # Bước 2: Hoàn tất nạp CSDL (nếu mức tự chủ là L2 hoặc có cờ --finish)
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
    """Giao diện dòng lệnh chính của bộ điều phối article_tick.

    Args:
        argv: Danh sách tham số dòng lệnh.

    Returns:
        Mã thoát tiến trình.
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


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
