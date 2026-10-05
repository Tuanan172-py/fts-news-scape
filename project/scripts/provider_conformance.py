"""Chấm độ phù hợp của provider với bộ vàng Article Lane, chi phí 0 token."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.conformance import MARGIN, check_against_baseline, score_outputs  # noqa: E402
from src.core.stdio import force_utf8_stdio                                      # noqa: E402

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = PROJECT_ROOT / "data" / "agent_tasks" / "article"
OUT_DIR = PROJECT_ROOT / "data" / "agent_outputs_article"
BASELINE_PATH = PROJECT_ROOT / "data" / "conformance" / "baseline_agy.json"


def _score(args: argparse.Namespace) -> dict:
    """Chấm các lô theo bộ vàng từ tham số dòng lệnh.

    Args:
        args: Tham số đã phân tích, cần `gold`, `batches`, `output_dir`, `task_dir`.

    Returns:
        Số đo của các lô.
    """
    gold_doc = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    gold = {str(a["article_id"]): a for a in gold_doc["articles"]}
    batches = [b.strip() for b in args.batches.split(",") if b.strip()]
    return score_outputs(Path(args.output_dir), Path(args.task_dir), gold, batches)


def main(argv=None) -> int:
    """Chạy giao diện dòng lệnh chấm độ phù hợp provider.

    Args:
        argv: Danh sách tham số dòng lệnh. Mặc định lấy từ `sys.argv`.

    Returns:
        Mã thoát 0 khi đạt, 1 khi không đạt, 2 khi thiếu mức agy để so.
    """
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("baseline", "check"):
        p = sub.add_parser(name, help="Ghi mức agy" if name == "baseline" else "So với mức agy")
        p.add_argument("--gold", required=True, help="Tệp bộ vàng JSON: {\"articles\": [...]}")
        p.add_argument("--batches", required=True, help="Mã lô, cách nhau bằng dấu phẩy")
        p.add_argument("--output-dir", default=str(OUT_DIR))
        p.add_argument("--task-dir", default=str(TASK_DIR))
        p.add_argument("--baseline", default=str(BASELINE_PATH))
        if name == "check":
            p.add_argument("--margin", type=float, default=MARGIN)
    args = ap.parse_args(argv)

    score = _score(args)
    print(json.dumps(score, ensure_ascii=False, indent=1))
    base_path = Path(args.baseline)

    if args.cmd == "baseline":
        base_path.parent.mkdir(parents=True, exist_ok=True)
        base_path.write_text(json.dumps(score, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Đã ghi mức agy: {base_path}")
        return 0

    if not base_path.exists():
        print(f"Chưa có mức agy ở {base_path}. Chạy `baseline` với đầu ra của agy trước.")
        return 2
    baseline = json.loads(base_path.read_text(encoding="utf-8"))
    reasons = check_against_baseline(score, baseline, args.margin)
    if reasons:
        print("KHÔNG ĐẠT: " + "; ".join(reasons))
        return 1
    print("ĐẠT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
