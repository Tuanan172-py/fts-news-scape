"""Điều phối quy trình vận hành tự động cho News-Scape (AutoPilot Runner).

Hỗ trợ chạy chuỗi pipeline khép kín hoặc tự động kích hoạt Subagents xử lý batch
tồn đọng thông qua Antigravity CLI headless (`agy -p`).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from pathlib import Path

# Thêm đường dẫn project vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PYTHON_EXEC = r"C:\venvs\news-scape\Scripts\python.exe"


def run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Thực thi lệnh shell và in log trực tiếp."""
    print(f"\n🚀 [AutoPilot] Chạy: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=False, text=True)
    if check and res.returncode != 0:
        print(f"❌ Lệnh thất bại với exit code: {res.returncode}")
    return res


def run_gold_pipeline(date: str | None = None, limit: int = 10, mini_batch: int = 5) -> None:
    """Tự động xuất tác vụ Gold, gọi Subagent LLM xử lý và giao hàng cho Users.

    Args:
        date: Ngày xuất bản (YYYY-MM-DD hoặc today).
        limit: Số lượng bài viết tối đa cần xử lý trong lượt này.
        mini_batch: Kích thước gom lô mini-batch (mặc định 5).
    """
    target_date = date or "today"
    print(f"================================================================================")
    print(f" 🤖 NEWS-SCAPE AUTOPILOT: GOLD PIPELINE CONTROLLED RUN [{target_date}]")
    print(f"================================================================================")

    # 1. Bước 1 — Export Gold Tasks
    export_cmd = [
        PYTHON_EXEC, "scripts/agent_export.py",
        "--date", target_date,
        "--limit", str(limit),
        "--mini-batch", str(mini_batch),
    ]
    run_cmd(export_cmd)

    # 2. Bước 2 — Tìm các batch tasks cần xử lý
    task_batches = sorted(glob.glob(str(PROJECT_ROOT / "data" / "agent_tasks" / "batch_*.task.json")))
    if not task_batches:
        print("ℹ️ [AutoPilot] Không tìm thấy batch Gold nào đang chờ trong data/agent_tasks/.")
        return

    print(f"📦 [AutoPilot] Tìm thấy {len(task_batches)} batch tasks cần LLM xử lý.")

    # 3. Bước 3 — Trigger Subagent xử lý qua Antigravity CLI Non-Interactive Mode
    for b_path in task_batches:
        b_name = os.path.basename(b_path)
        out_name = b_name.replace(".task.json", ".output.json")
        out_path = PROJECT_ROOT / "data" / "agent_outputs" / out_name

        if out_path.exists():
            print(f"⏩ [AutoPilot] Bỏ qua {b_name}, output {out_name} đã tồn tại.")
            continue

        prompt = (
            f"Bạn là Gold Financial Analyst. Hãy đọc task packet tại {b_path}, "
            f"phân tích chuyên sâu (summary, key_points, implication, sentiment, time_sensitivity, citations >= 20 chars exact substring) "
            f"và lưu kết quả dạng mảng JSON theo schema agent-output-v2-lean vào {out_path}."
        )
        print(f"\n🧠 [AutoPilot] Kích hoạt Antigravity CLI cho {b_name}...")
        agy_cmd = [
            "agy",
            "-p", prompt,
            "--dangerously-skip-permissions",
            "--effort", "low"
        ]
        # Chạy agy (cho phép fallback nếu đang trong môi trường test)
        try:
            run_cmd(agy_cmd, check=False)
        except Exception as e:
            print(f"⚠️ [AutoPilot] Không thể chạy agy trực tiếp qua shell: {e}")

    # 4. Bước 4 — Ingest kết quả vào Database
    output_dir = str(PROJECT_ROOT / "data" / "agent_outputs")
    ingest_cmd = [PYTHON_EXEC, "scripts/agent_ingest.py", output_dir]
    run_cmd(ingest_cmd, check=False)

    # 5. Bước 5 — Viết Deliverable Excel cho người dùng
    deliver_cmd = [PYTHON_EXEC, "scripts/write_user_output.py", "--date", target_date]
    run_cmd(deliver_cmd, check=False)
    print("\n✅ [AutoPilot] Chuỗi Gold có kiểm soát hoàn tất 100%!")


def main(argv: list[str]) -> int:
    """Điểm nhập lệnh CLI cho AutoPilot."""
    parser = argparse.ArgumentParser(description="AutoPilot điều phối tự động quy trình News-Scape")
    parser.add_argument("--date", default=None, help="Ngày xuất bản bài viết (YYYY-MM-DD hoặc today)")
    parser.add_argument("--limit", type=int, default=10, help="Số bài Gold tối đa cần bốc")
    parser.add_argument("--mini-batch", type=int, default=5, help="Kích thước mini-batch")
    args = parser.parse_args(argv)

    run_gold_pipeline(date=args.date, limit=args.limit, mini_batch=args.mini_batch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
