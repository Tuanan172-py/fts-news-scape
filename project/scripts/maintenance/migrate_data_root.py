"""Viết lại đường dẫn lưu trong monocle.db về dạng tương đối theo gốc dữ liệu `data_root()`.

- Mặc định chỉ đếm (`--dry-run`), in số dòng cần đổi theo bảng và cột.
- `--apply` viết lại trong một transaction rồi in số dòng đã đổi.
- Dạng được viết lại: tương đối có tiền tố `data/` hoặc `project/data/`, tuyệt đối trỏ
  vào `.../project/data/...` của kho cũ, tuyệt đối nằm dưới gốc dữ liệu hiện hành.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.core import paths  # noqa: E402
from src.core.config import resolve_db_path  # noqa: E402
from src.core.stdio import force_utf8_stdio  # noqa: E402

# Bảng và cột chứa một đường dẫn trơn.
PATH_COLUMNS: tuple[tuple[str, str], ...] = (
    ("work_items", "package_path"),
    ("l1_tasks", "packet_path"),
    ("silver_failures", "meta_path"),
    ("periodic_reports", "html_path"),
)
# Bảng và cột chứa mảng JSON, mỗi phần tử có khoá `path`.
JSON_PATH_COLUMNS: tuple[tuple[str, str], ...] = (
    ("periodic_reports", "attachments_json"),
)

_OLD_REPO_RE = re.compile(r"^.*?[\\/]project[\\/]data[\\/](?P<rest>.+)$", re.IGNORECASE)


def rewrite_path(value: str | None, old_roots: tuple[str, ...] = ()) -> str | None:
    """Tính dạng mới của một đường dẫn đã lưu.

    Args:
        value: Giá trị đọc từ DB.
        old_roots: Các thư mục dữ liệu cũ bổ sung, tuyệt đối, ví dụ gốc `project/data`.

    Returns:
        Đường dẫn tương đối dấu gạch chéo xuôi khi cần đổi, None khi giữ nguyên.
    """
    if not value:
        return None
    p = Path(value)
    if p.is_absolute():
        for root in old_roots:
            try:
                return p.relative_to(Path(root)).as_posix()
            except ValueError:
                continue
        m = _OLD_REPO_RE.match(value)
        if m:
            return m.group("rest").replace("\\", "/")
        rel = paths.to_data_relative(value)
        return rel if rel != value else None
    new = paths.strip_legacy_prefix(value)
    return new if new != value else None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Liệt kê cột của một bảng.

    Args:
        conn: Kết nối SQLite.
        table: Tên bảng.

    Returns:
        Tập tên cột, rỗng khi bảng không tồn tại.
    """
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _plan_plain(conn: sqlite3.Connection, table: str, column: str,
                old_roots: tuple[str, ...]) -> list[tuple[str, int]]:
    """Lập danh sách cập nhật cho một cột đường dẫn trơn.

    Args:
        conn: Kết nối SQLite.
        table: Tên bảng.
        column: Tên cột.
        old_roots: Thư mục dữ liệu cũ bổ sung.

    Returns:
        Danh sách (giá trị mới, rowid).
    """
    rows = conn.execute(
        f"SELECT rowid, {column} FROM {table} WHERE {column} IS NOT NULL").fetchall()
    return [(new, rid) for rid, val in rows
            if (new := rewrite_path(val, old_roots)) is not None]


def _plan_json(conn: sqlite3.Connection, table: str, column: str,
               old_roots: tuple[str, ...]) -> list[tuple[str, int]]:
    """Lập danh sách cập nhật cho một cột JSON chứa khoá `path`.

    Args:
        conn: Kết nối SQLite.
        table: Tên bảng.
        column: Tên cột.
        old_roots: Thư mục dữ liệu cũ bổ sung.

    Returns:
        Danh sách (JSON mới, rowid).
    """
    out: list[tuple[str, int]] = []
    rows = conn.execute(
        f"SELECT rowid, {column} FROM {table} WHERE {column} IS NOT NULL").fetchall()
    for rid, raw in rows:
        try:
            items = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(items, list):
            continue
        changed = False
        for item in items:
            if isinstance(item, dict):
                new = rewrite_path(item.get("path"), old_roots)
                if new is not None:
                    item["path"] = new
                    changed = True
        if changed:
            out.append((json.dumps(items, ensure_ascii=False), rid))
    return out


def _apply_silver_failures(conn: sqlite3.Connection, updates: list[tuple[str, int]]) -> None:
    """Đổi khoá chính của `silver_failures`, gộp dòng trùng khoá mới.

    Dòng trùng giữ số lần thử lớn nhất và cờ dead-letter lớn nhất, như
    `ArticleStore.normalize_silver_failure_keys`.

    Args:
        conn: Kết nối SQLite đang trong transaction.
        updates: Danh sách (khoá mới, rowid).
    """
    for new, rid in updates:
        old = conn.execute("SELECT attempts, dead_letter FROM silver_failures WHERE rowid=?",
                           (rid,)).fetchone()
        if old is None:
            continue
        dup = conn.execute("SELECT rowid, attempts, dead_letter FROM silver_failures "
                           "WHERE meta_path=?", (new,)).fetchone()
        if dup:
            conn.execute("UPDATE silver_failures SET attempts=?, dead_letter=? WHERE rowid=?",
                         (max(old[0], dup[1]), max(old[1], dup[2]), dup[0]))
            conn.execute("DELETE FROM silver_failures WHERE rowid=?", (rid,))
        else:
            conn.execute("UPDATE silver_failures SET meta_path=? WHERE rowid=?", (new, rid))


def migrate(db_path: str | Path, *, apply: bool = False,
            old_roots: tuple[str, ...] = ()) -> dict[str, int]:
    """Đếm hoặc viết lại đường dẫn của mọi bảng đích.

    Args:
        db_path: Đường dẫn `monocle.db`.
        apply: True thì ghi trong một transaction, False thì chỉ đếm.
        old_roots: Thư mục dữ liệu cũ bổ sung, tuyệt đối.

    Returns:
        Ánh xạ `bảng.cột` sang số dòng cần đổi (hoặc đã đổi khi `apply`).
    """
    conn = sqlite3.connect(str(db_path))
    counts: dict[str, int] = {}
    try:
        plans: list[tuple[str, str, list[tuple[str, int]]]] = []
        for table, column in PATH_COLUMNS:
            if column in _table_columns(conn, table):
                plans.append((table, column, _plan_plain(conn, table, column, old_roots)))
        for table, column in JSON_PATH_COLUMNS:
            if column in _table_columns(conn, table):
                plans.append((table, column, _plan_json(conn, table, column, old_roots)))
        for table, column, updates in plans:
            counts[f"{table}.{column}"] = len(updates)
        if apply:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for table, column, updates in plans:
                    if table == "silver_failures":
                        _apply_silver_failures(conn, updates)
                    else:
                        conn.executemany(f"UPDATE {table} SET {column}=? WHERE rowid=?",
                                         updates)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    finally:
        conn.close()
    return counts


def main(argv: list[str] | None = None) -> int:
    """Chạy giao diện dòng lệnh chuyển đổi đường dẫn.

    Args:
        argv: Tham số dòng lệnh, None thì đọc `sys.argv`.

    Returns:
        Mã thoát 0 khi thành công.
    """
    force_utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="Chỉ đếm, không ghi (mặc định)")
    mode.add_argument("--apply", action="store_true", help="Viết lại trong một transaction")
    ap.add_argument("--db", default=None, help="Đường dẫn monocle.db (mặc định DB vận hành)")
    ap.add_argument("--old-root", action="append", default=[],
                    help="Thư mục dữ liệu cũ tuyệt đối, lặp lại được")
    args = ap.parse_args(argv)

    db_path = args.db or str(resolve_db_path())
    counts = migrate(db_path, apply=args.apply, old_roots=tuple(args.old_root))
    tag = "ĐÃ ĐỔI" if args.apply else "CẦN ĐỔI (dry-run)"
    print(f"DB        : {db_path}")
    print(f"data_root : {paths.data_root()}")
    for key, n in counts.items():
        print(f"{key:<36} {tag}: {n}")
    print(f"tổng      : {sum(counts.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
