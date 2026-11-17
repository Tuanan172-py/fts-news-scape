"""Forwarding stub for decommissioned doc_lint.py. Delegated to scripts/knowledge.py under ADR-0021 / Schema v2."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import knowledge as k  # noqa: E402

Finding = k.Finding
lint_markdown = k.lint_markdown
lint_python = k.lint_python
lint_html = k.lint_html
lint_repo = k.lint_presentation_repo
_CONTRACT_FM_RE = k._FRONTMATTER_RE


def main(argv: list[str] | None = None) -> int:
    """Run the lint and print the violations."""
    ap = argparse.ArgumentParser(description="Lint chuẩn trình bày tài liệu và giao diện (legacy stub)")
    ap.add_argument("--summary", action="store_true", help="Chỉ in số vi phạm theo luật")
    args = ap.parse_args(argv)
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    findings = k.lint(REPO_ROOT)
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    if args.summary:
        by_code: dict[str, int] = {}
        for f in findings:
            by_code[f.code] = by_code.get(f.code, 0) + 1
        for rule in sorted(by_code):
            print(f"{rule}: {by_code[rule]}")
    else:
        for f in findings:
            print(f)
    print(f"Tổng: {len(errors)} lỗi, {len(warnings)} cảnh báo")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
