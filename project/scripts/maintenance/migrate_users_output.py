"""Di chuyển tệp giao hàng cũ từ `<gốc>/users_output` sang `<gốc>/users/output` (ADR-0026.D6)."""

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
    """Kết quả di chuyển.

    Attributes:
        moved: Số tệp đã (hoặc sẽ) chuyển.
        identical: Số tệp đã có ở đích với nội dung giống hệt, bỏ nguồn.
        conflicts: Đường dẫn tương đối của tệp đích đã có nhưng khác nội dung, giữ nguyên cả hai.
        removed_dirs: Số thư mục nguồn rỗng đã dọn.
    """

    moved: int = 0
    identical: int = 0
    conflicts: list[str] = field(default_factory=list)
    removed_dirs: int = 0


def migrate(source: Path, target: Path, apply: bool = False) -> MigrationReport:
    """Chuyển toàn bộ tệp từ cây cũ sang cây mới, không ghi đè tệp đích khác nội dung.

    Args:
        source: Thư mục cũ `users_output`.
        target: Thư mục mới `users/output`.
        apply: False chỉ đếm (chạy thử); True mới chuyển thật.

    Returns:
        MigrationReport với số liệu và danh sách xung đột.
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
    """Chạy lệnh dòng lệnh; mặc định chạy thử, thêm `--apply` để chuyển thật.

    Args:
        argv: Tham số dòng lệnh; None dùng `sys.argv`.

    Returns:
        0 khi không có xung đột, 1 khi còn tệp xung đột cần xử lý tay.
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
