"""Drive rolling waves that clear the article backlog with the OpenCode free tier."""
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

_PROJECT_DIR = str(Path(__file__).resolve().parents[1])
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

from src.core.paths import PROJECT_ROOT, article_packets_dir
from src.core.staging import safe_json_dump
from src.core.stdio import force_utf8_stdio

force_utf8_stdio()

PYTHON = sys.executable
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
ARTICLE_RUN = SCRIPTS_DIR / "article_run.py"
WRITE_OUTPUT = SCRIPTS_DIR / "write_user_output.py"
LOGS_DIR = Path("C:/data/news-scape/logs")
STATUS_FILE = LOGS_DIR / "backlog_opencode_status.json"


def record_status(payload: dict[str, Any]) -> None:
    """Write the wave progress state to the monitoring status file.

    Args:
        payload: Progress data to write; `updated_at` is added in place.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        safe_json_dump(payload, STATUS_FILE)
    except Exception:
        pass


def run_command(cmd: list[str], *, desc: str) -> tuple[int, str]:
    """Run a child command and print its progress.

    Args:
        cmd: Command and arguments.
        desc: Short description of the step.

    Returns:
        Pair of (exit code, captured stdout).
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {desc}...", flush=True)
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        print(f"   ⚠️ Lỗi (mã {proc.returncode}): {proc.stderr[:300].strip()}", flush=True)
    else:
        # Print the last few summary lines.
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        for line in lines[-3:]:
            print(f"   ✓ {line}", flush=True)
    return proc.returncode, proc.stdout


def main(argv: list[str] | None = None) -> int:
    """Run the rolling-wave loop that clears the backlog.

    Args:
        argv: Command-line arguments; defaults to `sys.argv[1:]`.

    Returns:
        Exit code 0 on clean completion.
    """
    ap = argparse.ArgumentParser(description="Tự động giải phóng bài viết tồn đọng qua OpenCode Runner")
    ap.add_argument("--waves", type=int, default=40, help="Số đợt tối đa cần chạy (mặc định 40)")
    ap.add_argument("--limit", type=int, default=250, help="Số bài tối đa trong mỗi đợt (mặc định 250 bài = 5 lô con)")
    ap.add_argument("--concurrency", type=int, default=2, help="Số lô chạy song song trong mỗi đợt (mặc định 2)")
    ap.add_argument("--runner", default="opencode", choices=["opencode", "agy", "openrouter"], help="Runner nhận thức")
    ap.add_argument("--min-coverage", type=float, default=0.20, help="Độ phủ tối thiểu để nạp CSDL cuốn chiếu (mặc định 0.20 = 20%%)")
    ap.add_argument("--cooldown", type=int, default=10, help="Thời gian nghỉ (giây) giữa các đợt (mặc định 10)")
    ap.add_argument("--max-runtime-hours", type=float, default=6.0, help="Trần thời gian tự dừng (giờ, mặc định 6.0)")
    ap.add_argument("--dry-run", action="store_true", help="Chỉ đóng gói, không gọi phân tích và nạp CSDL")
    args = ap.parse_args(argv)

    start_time = time.time()
    max_runtime_sec = args.max_runtime_hours * 3600
    total_processed_articles = 0
    waves_completed = 0

    print("=" * 84)
    print(" 🚀  KHỞI ĐỘNG TIẾN TRÌNH GIẢI PHÓNG BÀI TỒN ĐỌNG (HEADLESS ROLLING WAVES)")
    print(f"     • Mục tiêu: tối đa {args.waves} waves | {args.limit} bài/wave | Runner: {args.runner}")
    print(f"     • Trần thời gian ngân sách: {args.max_runtime_hours} giờ ({max_runtime_sec:,} giây)")
    print(f"     • Concurrency: {args.concurrency} luồng | Cooldown giữa các đợt: {args.cooldown} giây")
    print(f"     • Tệp giám sát trực tiếp: {STATUS_FILE}")
    print("=" * 84)

    record_status({
        "status": "RUNNING",
        "waves_target": args.waves,
        "limit_per_wave": args.limit,
        "waves_completed": 0,
        "articles_processed": 0,
        "current_wave": None,
    })

    for wave_idx in range(1, args.waves + 1):
        elapsed = time.time() - start_time
        if elapsed >= max_runtime_sec:
            print(f"\n⚠️ Đã chạm trần thời gian ngân sách ({args.max_runtime_hours}h). Tự động dừng sạch.")
            break

        timestamp_str = datetime.now().strftime("%m%d%H%M")
        wave_id = f"W_OPCD_{wave_idx:02d}_{timestamp_str}"

        print(f"\n[{wave_idx}/{args.waves}] Bắt đầu đợt {wave_id} ({args.limit} bài)...")
        record_status({
            "status": "RUNNING",
            "current_wave": wave_id,
            "wave_index": wave_idx,
            "waves_completed": waves_completed,
            "articles_processed": total_processed_articles,
            "step": "prepare",
        })

        # Step 1: pack the wave.
        pack_cmd = [
            PYTHON, str(ARTICLE_RUN),
            "--wave", wave_id,
            "--limit", str(args.limit),
            "--runner", args.runner,
            "--mode", "backlog",
            "--force",
        ]
        rc, out = run_command(pack_cmd, desc=f"Đóng gói bài viết đợt {wave_id}")
        if rc != 0:
            print(f"❌ Đóng gói đợt {wave_id} thất bại. Dừng tiến trình.")
            break

        manifest_path = article_packets_dir() / f"wave_{wave_id}.json"
        if not manifest_path.exists():
            print(f"❌ Không tìm thấy manifest {manifest_path}. Dừng tiến trình.")
            break

        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            articles_count = manifest_data.get("articles", 0)
        except Exception:
            articles_count = 0

        if articles_count == 0:
            print(f"\n🎉 KHO BÀI TỒN ĐỌNG ĐÃ ĐƯỢC GIẢI PHÓNG HẾT! Không còn bài chờ phân tích.")
            record_status({
                "status": "FINISHED",
                "message": "Toàn bộ bài tồn đọng đã được giải phóng thành công",
                "waves_completed": waves_completed,
                "articles_processed": total_processed_articles,
            })
            break

        if args.dry_run:
            print(f"ⓘ  Dry-run: Đã đóng gói {articles_count} bài vào {wave_id}. Bỏ qua phân tích.")
            continue

        # Step 2: run the analysis.
        record_status({
            "status": "RUNNING",
            "current_wave": wave_id,
            "step": "analyze",
            "articles_in_wave": articles_count,
        })
        analyze_cmd = [
            PYTHON, str(ARTICLE_RUN),
            "--wave", wave_id,
            "--runner", args.runner,
            "--mode", "backlog",
            "--force",
            "--analyze",
            "--concurrency", str(args.concurrency),
        ]
        rc, out = run_command(analyze_cmd, desc=f"Phân tích nhận thức {wave_id} qua {args.runner}")

        # Step 3: repair pass for articles that were missed.
        record_status({
            "status": "RUNNING",
            "current_wave": wave_id,
            "step": "repair",
        })
        repair_cmd = [
            PYTHON, str(ARTICLE_RUN),
            "--wave", wave_id,
            "--runner", args.runner,
            "--mode", "backlog",
            "--force",
            "--repair",
            "--concurrency", str(args.concurrency),
        ]
        run_command(repair_cmd, desc=f"Kiểm tra và vá bài sót {wave_id}")

        # Step 4: finish and load results into the SQLite monocle.db.
        record_status({
            "status": "RUNNING",
            "current_wave": wave_id,
            "step": "finish",
        })
        finish_cmd = [
            PYTHON, str(ARTICLE_RUN),
            "--wave", wave_id,
            "--runner", args.runner,
            "--mode", "backlog",
            "--finish",
            "--force",
            "--min-coverage", str(args.min_coverage),
        ]
        rc_finish, out_finish = run_command(finish_cmd, desc=f"Kiểm định DoD và nạp CSDL cho {wave_id}")

        # Step 5: refresh the Excel deliverables when the finish step succeeded.
        if rc_finish == 0:
            total_processed_articles += articles_count
            waves_completed += 1
            run_command([PYTHON, str(WRITE_OUTPUT), "--force"], desc="Cập nhật tệp giao hàng deliverable Excel")
            print(f"✅ Đợt {wave_id} hoàn tất thành công: +{articles_count} bài (Lũy kế: {total_processed_articles:,} bài).")
        else:
            print(f"⚠️ Đợt {wave_id} nạp CSDL có cảnh báo, tiếp tục đợt sau.")

        record_status({
            "status": "RUNNING",
            "waves_completed": waves_completed,
            "articles_processed": total_processed_articles,
            "last_completed_wave": wave_id,
        })

        if wave_idx < args.waves:
            print(f"💤 Tạm nghỉ {args.cooldown} giây làm mát kết nối mạng...")
            time.sleep(args.cooldown)

    total_time = round(time.time() - start_time, 1)
    print("\n" + "=" * 84)
    print(f" 🏁  KẾT THÚC TIẾN TRÌNH: Đã hoàn tất {waves_completed}/{args.waves} đợt.")
    print(f"     • Tổng số bài đã phân tích và nạp DB: {total_processed_articles:,} bài.")
    print(f"     • Tổng thời gian thực thi: {total_time} giây (~{round(total_time / 60, 1)} phút).")
    print("=" * 84)

    record_status({
        "status": "COMPLETED",
        "waves_completed": waves_completed,
        "articles_processed": total_processed_articles,
        "total_runtime_seconds": total_time,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
