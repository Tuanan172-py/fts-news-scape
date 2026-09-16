"""Dọn dẹp và di dời các task packet cũ còn tồn đọng tại thư mục gốc data/agent_tasks."""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path

# Cấu hình UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_ROOT.parent
SRC_TASKS_DIR = REPO_ROOT / "data" / "agent_tasks"
ARCHIVE_DIR = PROJECT_ROOT / "data" / "agent_tasks" / "archive" / "legacy_root"
DB_PATH = Path("C:/data/news-scape/monocle.db")


def cleanup_legacy_root_tasks() -> None:
    """Quét và di dời các task packet ở repo-root data/agent_tasks sang thư mục archive."""
    if not SRC_TASKS_DIR.exists():
        print(f"Thư mục {SRC_TASKS_DIR} không tồn tại.")
        return

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    legacy_files = list(SRC_TASKS_DIR.glob("*.task.json"))
    legacy_l1_files = list((SRC_TASKS_DIR / "l1").glob("*.task.json")) if (SRC_TASKS_DIR / "l1").exists() else []

    print(f"Tìm thấy {len(legacy_files)} task Gold và {len(legacy_l1_files)} task L1 tại thư mục gốc {SRC_TASKS_DIR}")

    moved_count = 0
    for f in legacy_files:
        dest = ARCHIVE_DIR / f.name
        shutil.move(str(f), str(dest))
        moved_count += 1

    (ARCHIVE_DIR / "l1").mkdir(parents=True, exist_ok=True)
    for f in legacy_l1_files:
        dest = ARCHIVE_DIR / "l1" / f.name
        shutil.move(str(f), str(dest))
        moved_count += 1

    print(f"Đã di dời an toàn {moved_count} tệp task packet cũ vào {ARCHIVE_DIR}")


if __name__ == "__main__":
    cleanup_legacy_root_tasks()
