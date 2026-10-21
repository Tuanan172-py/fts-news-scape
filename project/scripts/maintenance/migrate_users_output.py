"""Move legacy delivery files from `<root>/users_output` to `<root>/users/output` (ADR-0026.D6)."""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.core import paths
from src.core.stdio import force_utf8_stdio

LEGACY_NAME = "users_output"


@dataclass
class MigrationReport:
    """Outcome of a migration run.

    Attributes:
        moved: Number of files moved (or to be moved).
        identical: Number of files already present at the target with identical content; the source is dropped.
        conflicts: Relative paths whose target exists with different content; both copies are kept.
        removed_dirs: Number of empty source directories removed.
    """

    moved: int = 0
    identical: int = 0
    conflicts: list[str] = field(default_factory=list)
    removed_dirs: int = 0


def migrate(source: Path, target: Path, apply: bool = False) -> MigrationReport:
    """Move all files from the legacy tree to the new tree without overwriting differing targets.

    Args:
        source: Legacy `users_output` directory.
        target: New `users/output` directory.
        apply: False only counts (dry run); True performs the move.

    Returns:
        MigrationReport with the counts and the conflict list.
    """
    report = MigrationReport()
    if not source.is_dir():
        return report
    for src in sorted(p for p in source.rglob("*") if p.is_file()):
        rel = src.relative_to(source)
        dst = target / rel
        if dst.exists():
            if filecmp.cmp(src, dst, shallow=False):
                report.identical += 1
                if apply:
                    src.unlink()
            else:
                report.conflicts.append(rel.as_posix())
            continue
        report.moved += 1
        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
    if apply:
        for d in sorted((p for p in source.rglob("*") if p.is_dir()), reverse=True):
            if not any(d.iterdir()):
                d.rmdir()
                report.removed_dirs += 1
        if not any(source.iterdir()):
            source.rmdir()
            report.removed_dirs += 1
    return report


def main(argv: list[str] | None = None) -> int:
    """Run the command-line interface; dry run by default, `--apply` performs the move.

    Args:
        argv: Command-line arguments; None uses `sys.argv`.

    Returns:
        0 when there are no conflicts, 1 when conflicting files need manual handling.
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Chuyển thật (mặc định chỉ chạy thử).")
    args = ap.parse_args(argv)
    force_utf8_stdio()
    target = paths.users_output_dir()
    source = paths.data_root() / LEGACY_NAME
    rep = migrate(source, target, apply=args.apply)
    mode = "ĐÃ CHUYỂN" if args.apply else "CHẠY THỬ"
    print(f"[{mode}] {source} -> {target}")
    print(f"  chuyển: {rep.moved} | trùng nội dung: {rep.identical} | "
          f"xung đột: {len(rep.conflicts)} | thư mục rỗng đã dọn: {rep.removed_dirs}")
    for c in rep.conflicts:
        print(f"  XUNG ĐỘT (giữ cả hai): {c}")
    return 1 if rep.conflicts else 0


if __name__ == "__main__":
    sys.exit(main())
