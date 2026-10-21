"""Scan and clean OneDrive sync-conflict files in the project directory."""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Locate the repo root.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
if (REPO_ROOT / "project").exists():
    pass
elif (REPO_ROOT.parent / "project").exists():
    REPO_ROOT = REPO_ROOT.parent

# Hostnames known to produce conflicts on the project OneDrive.
KNOWN_HOSTNAMES = {"FPA-AnPT", "DESKTOP-RSG7M2C"}
comp_name = os.environ.get("COMPUTERNAME", "")
if comp_name:
    KNOWN_HOSTNAMES.add(comp_name)

host_subpattern = "|".join(re.escape(h) for h in sorted(KNOWN_HOSTNAMES) if h)

# Conflict suffix regex: -FPA-AnPT, -DESKTOP-RSG7M2C, - Copy, (1).
CONFLICT_RE = re.compile(
    rf"(-({host_subpattern})| - Copy.*|\s*\(\d+\))$",
    re.IGNORECASE
)


def sha256_file(path: Path) -> str:
    """Compute the SHA-256 hash of a file.

    Args:
        path: File to hash.

    Returns:
        Hex digest of the file content.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def find_conflicts(scan_root: Path) -> list[tuple[str, Path, Path | None]]:
    """Scan for OneDrive conflict files and classify the action for each.

    Action codes in the returned tuples:
      - `delete_lock`: temporary Office lock file (`~$*`)
      - `delete_tmp`: leftover temporary file (`.tmp`)
      - `rename_conflict`: only copy exists, rename it to the canonical name
      - `promote_conflict`: conflict copy is newer than or equal to the original, replace the original
      - `delete_duplicate`: identical size and SHA-256, delete the redundant conflict copy
      - `delete_older_conflict`: conflict copy is older than the original, delete it

    Args:
        scan_root: Directory to scan recursively.

    Returns:
        List of tuples `(action, conflict_path, canonical_path_or_none)`.
    """
    items = []
    
    # Skip unrelated directories.
    ignore_dirs = {".git", ".pytest_cache", "__pycache__", ".venv", "node_modules", "archive_conflicts"}

    for root, dirs, files in os.walk(scan_root):
        # Prune ignored directories in place.
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        cur_dir = Path(root)

        for fname in files:
            p = cur_dir / fname

            # 1. Office lock file.
            if fname.startswith("~$"):
                items.append(("delete_lock", p, None))
                continue

            # 2. Leftover temporary file.
            if fname.endswith(".tmp") or ".tmp." in fname:
                items.append(("delete_tmp", p, None))
                continue

            # 3. File with a conflict suffix.
            stem = p.stem
            suffix = p.suffix
            match = CONFLICT_RE.search(stem)
            if match:
                clean_stem = stem[:match.start()]
                canonical_path = cur_dir / f"{clean_stem}{suffix}"
                
                # Canonical file missing: rename this conflict copy to the canonical name.
                if not canonical_path.exists():
                    items.append(("rename_conflict", p, canonical_path))
                else:
                    # Canonical file exists: compare in detail so the latest edit is never lost.
                    try:
                        p_stat = p.stat()
                        canon_stat = canonical_path.stat()

                        # 3a. Identical binary content (SHA-256): delete the redundant copy.
                        if p_stat.st_size == canon_stat.st_size and sha256_file(p) == sha256_file(canonical_path):
                            items.append(("delete_duplicate", p, canonical_path))
                        # 3b. Conflict copy has mtime newer than or equal to the canonical (local user edit): promote.
                        elif p_stat.st_mtime >= canon_stat.st_mtime:
                            items.append(("promote_conflict", p, canonical_path))
                        # 3c. Canonical is strictly newer, so the conflict copy is stale: delete it.
                        else:
                            items.append(("delete_older_conflict", p, canonical_path))
                    except Exception:
                        pass

    return items


def main() -> int:
    """Scan for OneDrive conflict files and apply or preview the cleanup.

    Returns:
        Process exit code, always 0.
    """
    parser = argparse.ArgumentParser(description="Dọn dẹp và hợp nhất file conflict OneDrive an toàn")
    parser.add_argument("--path", type=str, default=str(REPO_ROOT),
                        help="Thư mục bắt đầu quét (mặc định: Repo Root)")
    parser.add_argument("--apply", action="store_true",
                        help="Thực hiện xóa/đổi tên/promote thật (mặc định: dry-run chỉ xem)")
    args = parser.parse_args()

    scan_dir = Path(args.path).resolve()
    print(f"[*] Quét file xung đột tại: {scan_dir}")
    print(f"[*] Chế độ: {'APPLY (Thực thi)' if args.apply else 'DRY-RUN (Chỉ kiểm tra)'}\n")

    items = find_conflicts(scan_dir)

    if not items:
        print("[OK] Không tìm thấy bất kỳ file xung đột hoặc lock file nào. Cây thư mục sạch sẽ!")
        return 0

    counts = {
        "delete_lock": 0,
        "delete_tmp": 0,
        "rename_conflict": 0,
        "promote_conflict": 0,
        "delete_duplicate": 0,
        "delete_older_conflict": 0,
    }
    
    print(f"Tìm thấy {len(items)} file cần xử lý:")
    for action, p, target in items:
        counts[action] = counts.get(action, 0) + 1
        rel_p = p.relative_to(scan_dir) if p.is_relative_to(scan_dir) else p
        
        if action == "delete_lock":
            print(f"  - [LOCK]    Xóa file khóa Office: {rel_p}")
            if args.apply:
                try:
                    p.unlink(missing_ok=True)
                except Exception as e:
                    print(f"    ! Lỗi xóa: {e}")
        elif action == "delete_tmp":
            print(f"  - [TMP]     Xóa file tạm: {rel_p}")
            if args.apply:
                try:
                    p.unlink(missing_ok=True)
                except Exception as e:
                    print(f"    ! Lỗi xóa: {e}")
        elif action == "rename_conflict":
            rel_t = target.relative_to(scan_dir) if target.is_relative_to(scan_dir) else target
            print(f"  - [RENAME]  Đổi tên bản conflict thành chuẩn: {rel_p} -> {rel_t.name}")
            if args.apply:
                try:
                    p.rename(target)
                except Exception as e:
                    print(f"    ! Lỗi đổi tên: {e}")
        elif action == "promote_conflict":
            rel_t = target.relative_to(scan_dir) if target.is_relative_to(scan_dir) else target
            print(f"  - [PROMOTE] Bản conflict MỚI HƠN -> Cập nhật thành file chính: {rel_p} -> {rel_t.name}")
            if args.apply:
                try:
                    # Overwrite the canonical file with the newer copy, then delete the conflict file.
                    shutil.copy2(p, target)
                    p.unlink(missing_ok=True)
                except Exception as e:
                    print(f"    ! Lỗi promote: {e}")
        elif action == "delete_duplicate":
            rel_t = target.relative_to(scan_dir) if target.is_relative_to(scan_dir) else target
            print(f"  - [DUP]     Trùng khớp 100% SHA256 -> Xóa bản sao thừa: {rel_p}")
            if args.apply:
                try:
                    p.unlink(missing_ok=True)
                except Exception as e:
                    print(f"    ! Lỗi xóa: {e}")
        elif action == "delete_older_conflict":
            rel_t = target.relative_to(scan_dir) if target.is_relative_to(scan_dir) else target
            print(f"  - [OLDER]   Bản conflict CŨ HƠN file chính -> Xóa bản sao cũ: {rel_p}")
            if args.apply:
                try:
                    p.unlink(missing_ok=True)
                except Exception as e:
                    print(f"    ! Lỗi xóa: {e}")

    print("\n" + "=" * 60)
    print("TỔNG KẾT:")
    print(f"  - File lock Office (~$*):                {counts['delete_lock']}")
    print(f"  - File tạm (.tmp*):                      {counts['delete_tmp']}")
    print(f"  - Bản conflict duy nhất (đổi tên):        {counts['rename_conflict']}")
    print(f"  - Bản conflict MỚI HƠN (cập nhật chính): {counts['promote_conflict']}")
    print(f"  - Bản trùng khớp 100% (xóa thừa):        {counts['delete_duplicate']}")
    print(f"  - Bản conflict cũ hơn (xóa cũ):          {counts['delete_older_conflict']}")
    print(f"  - Tổng số tác vụ:                        {len(items)}")
    print("=" * 60)

    if not args.apply:
        print("\n[!] Đây là DRY-RUN. Chạy lại với cờ `--apply` để thực thi xử lý:")
        print(f"    & \"C:\\venvs\\news-scape\\Scripts\\python.exe\" project/scripts/maintenance/clean_onedrive_conflicts.py --apply")
    else:
        print("\n[OK] Đã hoàn tất xử lý và hợp nhất an toàn toàn bộ file xung đột OneDrive!")

    return 0


if __name__ == "__main__":
    sys.exit(main())

