"""Smoke test các CLI entry point — chạy THẬT qua subprocess.

Lý do tồn tại: toàn bộ test còn lại đều import hàm trực tiếp, không test nào đi qua khối
`if __name__ == "__main__"`. Hai lỗi thật đã lọt lưới vì đúng điểm mù này (2026-09-17):

1. `__doc__.split("\\n")[1]` → IndexError ngay dòng đầu khi docstring module chỉ có 1 dòng.
2. `UnicodeEncodeError` khi in tiếng Việt/emoji lúc stdout là PIPE (encoding cp1252).

Cả hai nằm trên đường morninger gọi subprocess mỗi 5 phút, nên chúng vô hiệu hoá âm thầm
tính năng auto-drain mà vẫn để 403 test xanh.
"""

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Script được automation gọi (morninger · run_daily.ps1 · auto_pilot.py · news_cron · radar).
# Hỏng ở đây nghĩa là hỏng sản xuất một cách âm thầm.
AUTOMATION_CLIS = [
    "scripts/maintenance/backfill_deferred.py",
    "scripts/l1_route.py",
    "scripts/l1_ingest.py",
    "scripts/agent_export.py",
    "scripts/agent_ingest.py",
    "scripts/compile_users.py",
    "scripts/write_user_output.py",
    "scripts/monitor_daily.py",
    "scripts/fetch_periodic_reports.py",
    "scripts/pipeline_radar.py",
]


@pytest.mark.parametrize("script", AUTOMATION_CLIS)
def test_cli_help_runs_clean_through_pipe(script):
    """`--help` phải chạy sạch khi stdout là PIPE — mô phỏng đúng subprocess của morninger.

    `capture_output=True` khiến stdout không phải console, nên Python dùng encoding hệ
    thống (cp1252 trên máy này) — đây chính là điều kiện làm lộ lỗi Unicode.
    """
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / script), "--help"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=90,
        encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, (
        f"{script} --help thoát với mã {proc.returncode}:\n{proc.stderr[-1000:]}")
    assert "Traceback" not in proc.stderr, (
        f"{script} --help ném traceback:\n{proc.stderr[-1000:]}")


def test_backfill_deferred_dry_run_is_safe_and_reports():
    """Đường auto-drain của morninger phải chạy trọn vẹn và in được báo cáo.

    Không `--fetch` nên không chạm mạng; vẫn đi qua toàn bộ argparse → truy vấn → in
    tổng kết (dòng tổng kết có emoji/tiếng Việt).
    """
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts/maintenance/backfill_deferred.py"),
         "--mode", "all", "--limit", "3", "--dry-run", "--budget-seconds", "30"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=120,
        encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, f"exit={proc.returncode}\n{proc.stderr[-1000:]}"
    assert "Traceback" not in proc.stderr, proc.stderr[-1000:]
    assert "backfill" in proc.stdout, f"thiếu dòng tổng kết:\n{proc.stdout[-500:]}"
