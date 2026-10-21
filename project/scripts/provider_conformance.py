"""Score provider conformance against the Article Lane gold set at zero token cost."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.conformance import MARGIN, check_against_baseline, score_outputs  # noqa: E402
from src.core import paths                             # noqa: E402
from src.core.stdio import force_utf8_stdio                                      # noqa: E402

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = paths.article_packets_dir()
OUT_DIR = paths.agent_outputs_dir("_article")
BASELINE_PATH = paths.data_root() / "conformance" / "baseline_agy.json"


def _score(args: argparse.Namespace) -> dict:
    """Score batches against the gold set using command-line arguments.

    Args:
        args: Parsed arguments; requires `gold`, `batches`, `output_dir` and `task_dir`.

    Returns:
        Metrics of the scored batches.
    """
    gold_doc = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    gold = {str(a["article_id"]): a for a in gold_doc["articles"]}
    batches = [b.strip() for b in args.batches.split(",") if b.strip()]
    return score_outputs(Path(args.output_dir), Path(args.task_dir), gold, batches)


def main(argv=None) -> int:
    """Run the provider conformance scoring CLI.

    Args:
        argv: Command-line arguments; defaults to `sys.argv`.

    Returns:
        Exit code 0 on pass, 1 on failure, 2 when the agy baseline is missing.
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
