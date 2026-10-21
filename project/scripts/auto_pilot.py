"""Run the Gold pipeline by launching subagents through the headless Antigravity CLI (`agy -p`), asking the operator to confirm before any token spend (ADR 0008)."""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Make the project root importable.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core import paths  # noqa: E402
from src.core.stdio import force_utf8_stdio  # noqa: E402

force_utf8_stdio()

# Prefer the interpreter running this script; fall back to the hard-coded path only when
# it cannot be determined, to stay consistent with the python lookup in run_daily.ps1.
PYTHON_EXEC = sys.executable or r"C:\venvs\news-scape\Scripts\python.exe"

# Rough estimate: Vietnamese UTF-8 text averages about 4 bytes per input token.
_BYTES_PER_TOKEN = 4


class CommandFailed(RuntimeError):
    """Signal a failed child command so the error is never swallowed silently."""


def run_cmd(cmd: list[str], check: bool = True,
            timeout: int = 1800) -> subprocess.CompletedProcess:
    """Run a child command and stream its output directly.

    Args:
        cmd: Command-line argument list.
        check: Raise `CommandFailed` on a non-zero exit code.
        timeout: Maximum run time in seconds.

    Returns:
        Completed child process.

    Raises:
        CommandFailed: If the command fails and `check=True`, or if it times out.
    """
    print(f"\n🚀 [AutoPilot] Chạy: {' '.join(cmd)}")
    try:
        res = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=False,
                             text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        msg = f"Lệnh quá hạn {timeout}s: {' '.join(cmd)}"
        print(f"❌ [AutoPilot] {msg}")
        raise CommandFailed(msg) from e
    if res.returncode != 0:
        msg = f"Lệnh thất bại (exit {res.returncode}): {' '.join(cmd)}"
        print(f"❌ [AutoPilot] {msg}")
        if check:
            raise CommandFailed(msg)
    return res


def _count_tasks(batch_path: str) -> int:
    """Count the articles in a batch packet.

    Args:
        batch_path: Path to the batch packet JSON file.

    Returns:
        Number of tasks, or 0 when the file cannot be read.
    """
    try:
        data = json.loads(Path(batch_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    tasks = data if isinstance(data, list) else data.get("tasks", [])
    return len(tasks) if isinstance(tasks, list) else 0


def _confirm_activation(batches: list[str], effort: str, skip_permissions: bool,
                        assume_yes: bool) -> bool:
    """Show the expected cost and ask for confirmation before spending tokens.

    Args:
        batches: Paths of the batch packets about to be processed.
        effort: Value of `--effort` that will be passed to `agy`.
        skip_permissions: Whether the `agy` permission prompt is bypassed.
        assume_yes: The operator explicitly passed `--yes`.

    Returns:
        True if the run is allowed.
    """
    total_articles = sum(_count_tasks(b) for b in batches)
    total_bytes = sum(Path(b).stat().st_size for b in batches if Path(b).exists())
    est_tokens = total_bytes // _BYTES_PER_TOKEN

    print("\n" + "=" * 78)
    print(" ⚠️  SẮP TIÊU THỤ TOKEN CỦA TÀI KHOẢN — CẦN XÁC NHẬN (ADR 0008)")
    print("=" * 78)
    print(f"   • Số batch sẽ xử lý      : {len(batches)}")
    print(f"   • Số bài trong các batch : {total_articles}")
    print(f"   • Token đầu vào ước tính : ~{est_tokens:,} (chưa tính đầu ra)")
    print(f"   • Mức effort             : {effort}")
    print(f"   • Bỏ qua hỏi quyền agy   : {'CÓ — rủi ro cao' if skip_permissions else 'không'}")
    print("=" * 78)

    if assume_yes:
        print("✅ [AutoPilot] Đã có cờ --yes do người vận hành tự khai. Tiếp tục.")
        return True
    if not sys.stdin.isatty():
        print("⛔ [AutoPilot] Không có terminal tương tác và không có cờ --yes.")
        print("   Từ chối tiêu thụ token khi chưa ai cấp quyền (ADR 0008 §2.1).")
        return False
    try:
        answer = input("Gõ 'yes' để cho phép chạy, bất kỳ phím nào khác để huỷ: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n⛔ [AutoPilot] Đã huỷ.")
        return False
    if answer.lower() != "yes":
        print("⛔ [AutoPilot] Người vận hành từ chối. Không gọi agent nào.")
        return False
    return True


def run_gold_pipeline(date: str | None = None, limit: int = 10, mini_batch: int = 5,
                      *, max_batches: int = 0, effort: str = "low",
                      skip_permissions: bool = False, assume_yes: bool = False) -> int:
    """Export Gold tasks, ask for permission, run subagents and deliver the output.

    Args:
        date: Publication date (YYYY-MM-DD or `today`).
        limit: Maximum number of Gold articles to pick.
        mini_batch: Batch grouping size.
        max_batches: Maximum number of batches per run; 0 means unlimited.
        effort: Effort level passed to `agy`.
        skip_permissions: Enable the `--dangerously-skip-permissions` flag of `agy`.
        assume_yes: Skip the confirmation prompt (the operator accepts responsibility).

    Returns:
        0 when every batch succeeds, 1 on a failed batch or a denied permission.
    """
    target_date = date or "today"
    print("=" * 78)
    print(f" 🤖 NEWS-SCAPE AUTOPILOT: GOLD PIPELINE CONTROLLED RUN [{target_date}]")
    print("=" * 78)

    run_cmd([PYTHON_EXEC, "scripts/agent_export.py", "--date", target_date,
             "--limit", str(limit), "--mini-batch", str(mini_batch)])

    task_batches = sorted(glob.glob(
        str(paths.agent_tasks_dir() / "batch_*.task.json")))
    if not task_batches:
        print("ℹ️ [AutoPilot] Không có batch Gold nào đang chờ trong data/agent_tasks/.")
        return 0

    if max_batches > 0 and len(task_batches) > max_batches:
        print(f"✂️ [AutoPilot] Giới hạn {max_batches}/{len(task_batches)} batch cho lượt này.")
        task_batches = task_batches[:max_batches]

    if shutil.which("agy") is None:
        print("⛔ [AutoPilot] Không tìm thấy `agy` trong PATH. Gold cần Antigravity CLI.")
        print("   Cài đặt và đưa vào PATH trước khi chạy (ADR 0008 §2.6).")
        return 1

    if not _confirm_activation(task_batches, effort, skip_permissions, assume_yes):
        return 1

    failures: list[str] = []
    done = 0
    for b_path in task_batches:
        b_name = os.path.basename(b_path)
        out_path = paths.agent_outputs_dir() / \
            b_name.replace(".task.json", ".output.json")
        if out_path.exists():
            print(f"⏩ [AutoPilot] Bỏ qua {b_name}, output đã tồn tại.")
            continue

        prompt = (
            f"Bạn là Gold Financial Analyst. Hãy đọc task packet tại {b_path}, "
            f"phân tích chuyên sâu (summary, key_points, implication, sentiment, "
            f"time_sensitivity, citations >= 20 chars exact substring) và lưu kết quả "
            f"dạng mảng JSON theo schema agent-output-v2-lean vào {out_path}."
        )
        agy_cmd = ["agy", "-p", prompt, "--effort", effort]
        if skip_permissions:
            print("⚠️ [AutoPilot] Chạy agy với --dangerously-skip-permissions theo yêu cầu.")
            agy_cmd.append("--dangerously-skip-permissions")

        print(f"\n🧠 [AutoPilot] Kích hoạt Antigravity CLI cho {b_name}...")
        try:
            run_cmd(agy_cmd)
        except CommandFailed as e:
            failures.append(f"{b_name}: {e}")
            continue
        # Exit code 0 does not guarantee that the output was produced; check the file.
        if not out_path.exists():
            failures.append(f"{b_name}: agy thoát 0 nhưng không sinh {out_path.name}")
            print(f"❌ [AutoPilot] {failures[-1]}")
            continue
        done += 1

    if done:
        try:
            run_cmd([PYTHON_EXEC, "scripts/agent_ingest.py",
                     str(paths.agent_outputs_dir())])
            run_cmd([PYTHON_EXEC, "scripts/write_user_output.py", "--date", target_date])
        except CommandFailed as e:
            failures.append(str(e))

    print("\n" + "-" * 78)
    if failures:
        print(f"❌ [AutoPilot] {done} batch thành công, {len(failures)} lỗi:")
        for f in failures:
            print(f"   • {f}")
        return 1
    print(f"✅ [AutoPilot] Hoàn tất {done}/{len(task_batches)} batch, không lỗi.")
    return 0


def main(argv: list[str]) -> int:
    """Parse the AutoPilot command line and run the Gold pipeline.

    Args:
        argv: Command-line arguments, excluding the program name.

    Returns:
        Exit code of the Gold pipeline run.
    """
    parser = argparse.ArgumentParser(
        description="AutoPilot điều phối quy trình Gold News-Scape")
    parser.add_argument("--date", default=None, help="Ngày xuất bản (YYYY-MM-DD hoặc today)")
    parser.add_argument("--limit", type=int, default=10, help="Số bài Gold tối đa cần bốc")
    parser.add_argument("--mini-batch", type=int, default=5, help="Kích thước mini-batch")
    parser.add_argument("--max-batches", type=int, default=0,
                        help="Trần số batch mỗi lượt chạy (0 = không giới hạn)")
    parser.add_argument("--effort", default="low", choices=["low", "medium", "high"],
                        help="Mức effort truyền cho agy")
    parser.add_argument("--yes", action="store_true",
                        help="Bỏ qua bước hỏi quyền — người vận hành tự chịu trách nhiệm chi phí")
    parser.add_argument("--skip-permissions", action="store_true",
                        help="Bật --dangerously-skip-permissions của agy (mặc định TẮT)")
    args = parser.parse_args(argv)

    return run_gold_pipeline(
        date=args.date, limit=args.limit, mini_batch=args.mini_batch,
        max_batches=args.max_batches, effort=args.effort,
        skip_permissions=args.skip_permissions, assume_yes=args.yes)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
