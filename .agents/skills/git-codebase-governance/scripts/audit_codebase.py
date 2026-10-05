"""Kiểm tra và tra soát đối chiếu toàn diện trạng thái Git, cấu trúc codebase và ranh giới kiến trúc."""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BLACKLIST_PATTERNS = [
    re.compile(r"\bnhìn chung\b", re.IGNORECASE),
    re.compile(r"\bthông thường\b", re.IGNORECASE),
    re.compile(r"\bnói chung\b", re.IGNORECASE),
    re.compile(r"\bvề cơ bản\b", re.IGNORECASE),
    re.compile(r"\bđáng chú ý\b", re.IGNORECASE),
    re.compile(r"\bcần lưu ý rằng\b", re.IGNORECASE),
    re.compile(r"\bđóng vai trò quan trọng\b", re.IGNORECASE),
    re.compile(r"\btoàn diện\b", re.IGNORECASE),
    re.compile(r"\bmạnh mẽ\b", re.IGNORECASE),
    re.compile(r"\bhiệu quả cao\b", re.IGNORECASE),
    re.compile(r"\btối ưu nhất\b", re.IGNORECASE),
    re.compile(r"\bchúng ta\b", re.IGNORECASE),
    re.compile(r"\btôi\b", re.IGNORECASE),
]

FORBIDDEN_EXTENSIONS = {".pyc", ".pyd", ".db", ".db-wal", ".db-shm", ".sqlite", ".zip", ".tar.gz"}


class AuditResult(NamedTuple):
    """Kết quả kiểm tra chi tiết từng hạng mục.

    Attributes:
        category: Tên danh mục kiểm tra.
        status: Trạng thái đánh giá (PASS, WARN, FAIL).
        details: Danh sách thông tin chi tiết hoặc tệp vi phạm.
    """
    category: str
    status: str
    details: list[str]


def run_git_command(args: list[str], cwd: Path) -> tuple[int, str]:
    """Thực thi lệnh git và trả về mã thoát cùng nội dung đầu ra.

    Args:
        args: Danh sách tham số dòng lệnh.
        cwd: Thư mục thực thi.

    Returns:
        Bộ giá trị gồm mã thoát và chuỗi đầu ra đã giải mã utf-8.
    """
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return proc.returncode, proc.stdout.strip()
    except Exception as exc:
        return 1, str(exc)


def check_git_status(repo_root: Path) -> list[AuditResult]:
    """Tra soát trạng thái vùng làm việc Git và đối chiếu remote.

    Args:
        repo_root: Đường dẫn gốc của repository.

    Returns:
        Danh sách các kết quả kiểm tra trạng thái Git.
    """
    results: list[AuditResult] = []

    # 1. Kiểm tra trạng thái làm việc (Working tree & Staged)
    code, out = run_git_command(["status", "--porcelain"], repo_root)
    if code != 0:
        results.append(AuditResult("Git Status", "FAIL", [f"Không thể chạy git status: {out}"]))
        return results

    modified_files = []
    untracked_files = []
    conflict_files = []

    for line in out.splitlines():
        if not line.strip():
            continue
        status_code = line[:2]
        file_path = line[3:].strip()
        if status_code == "??":
            untracked_files.append(file_path)
            if re.search(r"-[A-Z0-9]+-[A-Z0-9]+|-(FPA-AnPT|DESKTOP-)", file_path):
                conflict_files.append(file_path)
        else:
            modified_files.append(file_path)

    status_eval = "PASS" if not modified_files else "WARN"
    results.append(AuditResult(
        "Working Tree Changes",
        status_eval,
        [f"{len(modified_files)} tệp có thay đổi chưa commit."] if modified_files else ["Vùng làm việc sạch."],
    ))

    untracked_eval = "WARN" if untracked_files else "PASS"
    results.append(AuditResult(
        "Untracked Files",
        untracked_eval,
        [f"{len(untracked_files)} tệp chưa theo dõi."] if untracked_files else ["Không có tệp untracked."],
    ))

    conflict_eval = "FAIL" if conflict_files else "PASS"
    results.append(AuditResult(
        "OneDrive Conflict Files",
        conflict_eval,
        [f"{len(conflict_files)} tệp mang hậu tố xung đột máy trạm."] if conflict_files else ["Không có tệp conflict."],
    ))

    # 2. Kiểm tra Remote Tracking
    code_branch, cur_branch = run_git_command(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    if code_branch == 0:
        code_rev, rev_out = run_git_command(
            ["rev-list", "--left-right", "--count", f"HEAD...origin/{cur_branch}"],
            repo_root,
        )
        if code_rev == 0 and rev_out:
            parts = rev_out.split()
            if len(parts) == 2:
                ahead, behind = parts[0], parts[1]
                sync_details = [f"Nhánh hiện tại: {cur_branch}", f"Ahead: {ahead} commit(s)", f"Behind: {behind} commit(s)"]
                sync_eval = "PASS" if ahead == "0" and behind == "0" else "WARN"
                results.append(AuditResult("Remote Synchronization", sync_eval, sync_details))
            else:
                results.append(AuditResult("Remote Synchronization", "WARN", [f"Thông tin rev-list: {rev_out}"]))
        else:
            results.append(AuditResult("Remote Synchronization", "WARN", ["Chưa thiết lập upstream tracking."]))

    return results


def check_ast_and_syntax(repo_root: Path) -> AuditResult:
    """Kiểm tra tính hợp lệ của cú pháp AST trên toàn bộ tệp mã nguồn Python.

    Args:
        repo_root: Đường dẫn gốc của repository.

    Returns:
        Kết quả kiểm tra cú pháp AST.
    """
    syntax_errors: list[str] = []
    scanned_count = 0

    for py_file in repo_root.rglob("*.py"):
        # Bỏ qua thư mục venv, cache và file conflict
        if any(part in py_file.parts for part in {".venv", "__pycache__", ".pytest_cache", "build", "dist"}):
            continue
        if re.search(r"-[A-Z0-9]+-[A-Z0-9]+|-(FPA-AnPT|DESKTOP-)", py_file.name):
            continue

        scanned_count += 1
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
            ast.parse(content, filename=str(py_file))
        except Exception as exc:
            syntax_errors.append(f"{py_file.relative_to(repo_root)}: {exc}")

    status = "FAIL" if syntax_errors else "PASS"
    details = syntax_errors if syntax_errors else [f"Đã quét {scanned_count} tệp Python. Cú pháp hợp lệ 100%."]
    return AuditResult("Python AST Syntax", status, details)


def check_blacklisted_terms(repo_root: Path) -> AuditResult:
    """Quét và phát hiện các cụm từ thuộc danh mục từ cấm trong docstrings và mã nguồn.

    Args:
        repo_root: Đường dẫn gốc của repository.

    Returns:
        Kết quả kiểm tra danh mục từ cấm.
    """
    violations: list[str] = []
    src_dirs = [repo_root / "project" / "src", repo_root / "project" / "scripts"]

    for src_dir in src_dirs:
        if not src_dir.exists():
            continue
        for py_file in src_dir.rglob("*.py"):
            if re.search(r"-[A-Z0-9]+-[A-Z0-9]+|-(FPA-AnPT|DESKTOP-)", py_file.name):
                continue
            try:
                lines = py_file.read_text(encoding="utf-8", errors="replace").splitlines()
                for line_no, line in enumerate(lines, start=1):
                    # Chỉ kiểm tra comments hoặc chuỗi tài liệu
                    stripped = line.strip()
                    if not (stripped.startswith("#") or '"""' in line or "'''" in line):
                        continue
                    for pat in BLACKLIST_PATTERNS:
                        match = pat.search(line)
                        if match:
                            rel_path = py_file.relative_to(repo_root)
                            violations.append(f"{rel_path}:{line_no} chứa cụm từ cấm '{match.group(0)}'")
            except Exception:
                continue

    status = "WARN" if violations else "PASS"
    details = violations[:15] if violations else ["Không phát hiện từ cấm trong phạm vi src/ và scripts/."]
    if len(violations) > 15:
        details.append(f"... và thêm {len(violations) - 15} trường hợp khác.")
    return AuditResult("Rule 06 Blacklist Terms", status, details)


def check_forbidden_files_in_git(repo_root: Path) -> AuditResult:
    """Kiểm tra sự hiện diện của các tệp nhị phân hoặc dữ liệu cấm trong Git tracking.

    Args:
        repo_root: Đường dẫn gốc của repository.

    Returns:
        Kết quả kiểm tra tệp cấm được theo dõi.
    """
    code, out = run_git_command(["ls-files"], repo_root)
    if code != 0:
        return AuditResult("Tracked Files Sanity", "FAIL", [f"Không thể chạy git ls-files: {out}"])

    violations: list[str] = []
    for file_name in out.splitlines():
        path = Path(file_name)
        if path.suffix.lower() in FORBIDDEN_EXTENSIONS:
            violations.append(f"Tệp nhị phân bị theo dõi: {file_name}")
        if ".venv/" in file_name or file_name.startswith(".venv"):
            violations.append(f"Tệp môi trường ảo bị theo dõi: {file_name}")

    status = "FAIL" if violations else "PASS"
    details = violations if violations else ["Toàn bộ tệp được Git theo dõi đều hợp chuẩn."]
    return AuditResult("Tracked Files Sanity", status, details)


def main() -> int:
    """Thực thi quy trình kiểm tra và in bảng báo cáo trạng thái.

    Returns:
        Mã thoát 0 nếu thành công hoặc cảnh báo, 1 nếu có lỗi nghiêm trọng.
    """
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent.parent
    if not (repo_root / ".git").exists() and (repo_root.parent / ".git").exists():
        repo_root = repo_root.parent

    print(f"=== BÁO CÁO TRA SOÁT CODEBASE & KIẾN TRÚC GIT ===")
    print(f"Repository Root: {repo_root}")
    print("=" * 50)

    results: list[AuditResult] = []
    results.extend(check_git_status(repo_root))
    results.append(check_forbidden_files_in_git(repo_root))
    results.append(check_ast_and_syntax(repo_root))
    results.append(check_blacklisted_terms(repo_root))

    has_fail = False
    for res in results:
        indicator = "[PASS]" if res.status == "PASS" else ("[WARN]" if res.status == "WARN" else "[FAIL]")
        print(f"\n{indicator} {res.category}")
        for item in res.details:
            print(f"  - {item}")
        if res.status == "FAIL":
            has_fail = True

    print("\n" + "=" * 50)
    if has_fail:
        print("KẾT LUẬN: Phát hiện vi phạm nghiêm trọng cần xử lý trước khi thực hiện commit.")
        return 1
    print("KẾT LUẬN: Codebase và trạng thái Git đạt tiêu chuẩn quản trị.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
