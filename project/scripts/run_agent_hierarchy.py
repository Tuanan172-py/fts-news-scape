"""Orchestrate the multi-tier agent cycle and its quality verification."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core import paths  # noqa: E402
from src.core.stdio import force_utf8_stdio  # noqa: E402

force_utf8_stdio()


def get_task_counts() -> tuple[int, int]:
    """Count the task packets waiting for processing.

    Returns:
        Pair of (L1 packet count, Gold packet count).
    """
    l1_dir = paths.agent_tasks_dir() / "l1"
    gold_dir = paths.agent_tasks_dir()

    l1_count = len(list(l1_dir.glob("*.task.json"))) if l1_dir.exists() else 0
    gold_count = (
        len([p for p in gold_dir.glob("*.task.json") if p.is_file()])
        if gold_dir.exists()
        else 0
    )
    return l1_count, gold_count


def get_output_counts() -> tuple[int, int]:
    """Count the agent output JSON files already written.

    Returns:
        Pair of (L1 output count, Gold output count).
    """
    l1_out = paths.agent_outputs_dir("_l1")
    gold_out = paths.agent_outputs_dir()

    l1_count = len(list(l1_out.glob("*.json"))) if l1_out.exists() else 0
    gold_count = (
        len([p for p in gold_out.glob("*.json") if p.is_file()])
        if gold_out.exists()
        else 0
    )
    return l1_count, gold_count


def run_export(batch_size: int = 50, order: str = "desc", sync_silver: bool = True, mini_batch: int = 10,
               user: list[str] | None = None, date: str | None = None, days: int | None = None) -> bool:
    """Export task packets from work_items and l1_route in batches.

    Args:
        batch_size: Number of tasks per exported batch.
        order: Pick order, `desc` (newest first) or `asc` (oldest first).
        sync_silver: Re-derive Silver from Bronze before exporting.
        mini_batch: Articles per Gold mini-batch packet; 0 disables grouping.
        user: User names to filter the Gold packets by.
        date: Restrict export to one date (`YYYY-MM-DD`, `today`, `all`).
        days: Restrict export to the last N days.

    Returns:
        True if the Gold export succeeded, False otherwise.
    """
    if sync_silver:
        print("🔄 [Step 0] Kiểm tra và tự động đồng bộ Silver từ Bronze (rederive_incremental)...")
        res_derive = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.morninger",
                "--once",
                "derive",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(PROJECT_ROOT),
        )
        if res_derive.returncode != 0:
            print(f"  ⚠️ Cảnh báo re-derive Silver:\n{res_derive.stderr}", file=sys.stderr)
        else:
            found_summary = False
            for line in res_derive.stdout.splitlines():
                if "derive done:" in line or "checkpoint=" in line:
                    print(f"  • {line.strip()}")
                    found_summary = True
                    break
            if not found_summary:
                print("  • Silver đã đồng bộ hoàn tất.")

    print(f"\n🚀 [Step 1] Đang đồng bộ L1 Tasks và xuất task packets từ work_items (batch={batch_size}, order={order})...")
    # 1. Sync l1_route.
    res_l1 = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "l1_route.py"),
            "--batch-size",
            str(batch_size),
            "--order",
            order,
            "--review",
            "missed",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(PROJECT_ROOT),
    )
    if res_l1.returncode != 0:
        print(f"⚠️ Cảnh báo L1 route:\n{res_l1.stderr}", file=sys.stderr)
    else:
        print(f"  • L1 Route: {res_l1.stdout.strip().splitlines()[0] if res_l1.stdout.strip() else 'done'}")

    # 2. Run agent_export for Gold, with mini-batch grouping and subscriber filtering.
    gold_cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "agent_export.py"),
        "--batch-size",
        str(batch_size),
        "--order",
        order,
        "--subscriber-only",
    ]
    if mini_batch and mini_batch > 0:
        gold_cmd.extend(["--mini-batch", str(mini_batch)])
    if user:
        for u in user:
            gold_cmd.extend(["--user", str(u)])
    if date:
        gold_cmd.extend(["--date", str(date)])
    if days:
        gold_cmd.extend(["--days", str(days)])

    res_gold = subprocess.run(
        gold_cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(PROJECT_ROOT),
    )
    print(f"  • Gold Export: {res_gold.stdout.strip().splitlines()[0] if res_gold.stdout.strip() else 'done'}")

    if res_gold.returncode != 0:
        print(f"❌ Export thất bại:\n{res_gold.stderr}", file=sys.stderr)
        return False

    # 3. Show the summary table of the exported batches.
    from src.agent.manifest import load_batch_manifest, print_batch_summary_table
    gold_manifest = load_batch_manifest(paths.agent_tasks_dir())
    if gold_manifest:
        print_batch_summary_table(gold_manifest)

    return True


def run_ingest() -> bool:
    """Run the L1 and Agent ingest steps to verify the Definition-of-Done.

    Returns:
        True if both the L1 and Gold ingest processes exited with code 0.
    """
    print("\n🔍 [Step 2] Đang nghiệm thu Definition-of-Done (DoD Ingest)...")

    # Materialize code-first results first: most articles (route=resolved) need no agent,
    # and without this step they stay 'pending' forever because they never pass the export gate.
    # See docs/decisions/0003-code-first-l1-delivery.md.
    res_cf = subprocess.run(
        [sys.executable, "scripts/l1_ingest.py", "--code-first"],
        capture_output=True, text=True, encoding="utf-8", cwd=str(PROJECT_ROOT),
    )
    print(f"  - L1 code-first: {res_cf.stdout.strip()}")

    # Ingest L1
    l1_out_dir = str(paths.agent_outputs_dir("_l1"))
    res_l1 = subprocess.run(
        [sys.executable, "scripts/l1_ingest.py", l1_out_dir],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(PROJECT_ROOT),
    )
    print(f"  • L1 Ingest:\n    {res_l1.stdout.strip()}")

    # Ingest Gold
    gold_out_dir = str(paths.agent_outputs_dir())
    res_gold = subprocess.run(
        [sys.executable, "scripts/agent_ingest.py", gold_out_dir],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(PROJECT_ROOT),
    )
    print(f"  • Gold Ingest:\n    {res_gold.stdout.strip()}")

    return res_l1.returncode == 0 and res_gold.returncode == 0


def run_user_delivery() -> bool:
    """Compile and write the deliverables for users.

    Returns:
        True if the write_user_output process exited with code 0.
    """
    print("\n📦 [Step 3] Đang phân tuyến và xuất deliverable cá nhân hóa...")
    res = subprocess.run(
        [
            sys.executable,
            "scripts/write_user_output.py",
            "--date",
            "all",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(PROJECT_ROOT),
    )
    print(res.stdout.strip())
    return res.returncode == 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the selected orchestration steps.

    Args:
        argv: Command-line arguments; defaults to `sys.argv[1:]`.

    Returns:
        Process exit code, 1 if the export step fails, otherwise 0.
    """
    parser = argparse.ArgumentParser(
        description="Multi-Agent Hierarchy Orchestration Runner"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Kiểm tra trạng thái hàng đợi task và output",
    )
    parser.add_argument(
        "--export", action="store_true", help="Chạy xuất task packets"
    )
    parser.add_argument(
        "--ingest-and-deliver",
        action="store_true",
        help="Chạy Ingest DoD và xuất output người dùng",
    )
    parser.add_argument(
        "--full-cycle",
        action="store_true",
        help="Chạy toàn bộ chu trình từ Export đến User Output",
    )
    parser.add_argument(
        "--batch-size",
        "-b",
        type=int,
        default=50,
        help="Kích thước lô task xuất ra cho Subagents (mặc định: 50)",
    )
    parser.add_argument(
        "--order",
        choices=["desc", "asc"],
        default="desc",
        help="Thứ tự bốc việc: desc (mới nhất trước), asc (cũ nhất trước)",
    )

    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="Bỏ qua bước tự động đồng bộ Silver trước khi export",
    )
    parser.add_argument(
        "--batch-info",
        action="store_true",
        help="Xem bảng thông tin lô task packets hiện tại từ batch_manifest.json",
    )
    parser.add_argument(
        "--mini-batch",
        "-m",
        type=int,
        default=10,
        help="Gom lô thành các mini-batch packets cho Gold Agent (mặc định: 10 bài/packet)",
    )
    parser.add_argument(
        "--user",
        "-u",
        action="append",
        help="Lọc task packets theo người dùng cụ thể (vd: --user AnPT)",
    )
    parser.add_argument(
        "--days",
        "-d",
        type=int,
        default=None,
        help="Chỉ xuất bài trong N ngày gần nhất (tính từ ngày bài viết)",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Chỉ xuất bài trong ngày cụ thể (YYYY-MM-DD, today, all)",
    )
    args = parser.parse_args(argv)

    if args.batch_info:
        from src.agent.manifest import load_batch_manifest, print_batch_summary_table
        gold_manifest = load_batch_manifest(paths.agent_tasks_dir())
        l1_manifest = load_batch_manifest(paths.agent_tasks_dir() / "l1")
        if not gold_manifest and not l1_manifest:
            print(f"⚠️ Chưa có batch_manifest.json nào trong {paths.agent_tasks_dir()}. Vui lòng chạy --export trước.")
            return 0
        if gold_manifest:
            print_batch_summary_table(gold_manifest)
        if l1_manifest:
            print_batch_summary_table(l1_manifest)
        return 0

    if args.status or (
        not args.export and not args.ingest_and_deliver and not args.full_cycle
    ):
        l1_tasks, gold_tasks = get_task_counts()
        l1_outs, gold_outs = get_output_counts()
        print("==================================================")
        print("📊 TRẠNG THÁI HÀNG ĐỢI MULTI-AGENT HIERARCHY")
        print("==================================================")
        print(f"  • Hàng đợi L1 Tasks  : {l1_tasks} packets")
        print(f"  • Hàng đợi Gold Tasks: {gold_tasks} packets")
        print(f"  • Đã ghi L1 Outputs  : {l1_outs} files")
        print(f"  • Đã ghi Gold Outputs: {gold_outs} files")
        print("==================================================")
        return 0

    if args.export or args.full_cycle:
        if not run_export(
            batch_size=args.batch_size,
            order=args.order,
            sync_silver=not args.no_sync,
            mini_batch=args.mini_batch,
            user=args.user,
            date=args.date,
            days=args.days,
        ):
            return 1
        l1_tasks, gold_tasks = get_task_counts()
        print(
            f"✅ Đã sẵn sàng: {l1_tasks} L1 tasks, {gold_tasks} Gold tasks (batch={args.batch_size}, order={args.order}) cho Subagents Flash."
        )


    if args.ingest_and_deliver or args.full_cycle:
        if not run_ingest():
            print(
                "⚠️ Ingest có cảnh báo hoặc lỗi DoD. Vui lòng kiểm tra log."
            )
        run_user_delivery()
        print("\n✨ Hoàn tất chu trình điều phối Multi-Agent Hierarchy!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
