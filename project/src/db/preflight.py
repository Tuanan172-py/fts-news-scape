"""Resolve the operational database path and probe write access before spending tokens."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src.core.config import load_settings
from src.core.paths import REPO_ROOT



def resolve_db_path() -> Path:
    """Return the exact path that the ingestion scripts will write to.

    Priority order matches `ArticleStore`: environment variable `MONOCLE_DB_PATH`, then
    `MONOCLE_DATA_DIR`, then `database.path` in `settings.yaml`. A relative path is taken
    from the `project/` directory.

    Returns:
        Absolute path to `monocle.db`.

    Raises:
        UnsafeDatabasePathError: If the path is in OneDrive or the code repository.
    """
    return Path(load_settings()["database"]["path"])


@dataclass
class WriteProbe:
    """Result of a write-access probe on the database.

    Attributes:
        path: Database path that was probed.
        ok: True if the database is writable.
        reason: Short outcome description.
    """

    path: Path
    ok: bool
    reason: str

    @property
    def outside_workspace(self) -> bool:
        """Check whether the file lies outside the code repository directory.

        Returns:
            True if the path is not under the repository tree.
        """
        try:
            self.path.resolve().relative_to(REPO_ROOT.resolve())
            return False
        except ValueError:
            return True

    def hint(self) -> str:
        """Explain the real cause of a write failure as one actionable sentence.

        The raw sqlite3 error only says "attempt to write a readonly database", which sounds
        like a read-only file attribute and sends the fixer in the wrong direction. The most
        common cause on DSH is the `workspace-write` sandbox blocking writes outside the repository.

        Returns:
            Hint sentence, empty when the write probe succeeded.
        """
        if self.ok:
            return ""
        if self.outside_workspace:
            return (f"DB nằm ngoài kho mã ({self.path.parent}). Sandbox workspace-write "
                    f"chặn ghi ra ngoài kho. Không có cấu hình nào mở rộng được tập "
                    f"quyền ghi: `writableRoots` chỉ gồm workspace root và thư mục tạm. "
                    f"Chạy lệnh hoàn tất đợt (`--finish`) và lệnh giao hàng với "
                    f"danger-full-access; lệnh chuẩn bị đợt và bước chạy mô hình "
                    f"không cần quyền này.")
        return "Kiểm quyền ghi của thư mục chứa DB và các tệp -wal, -shm đi kèm."


def probe_write(path: Path | None = None, *, timeout: float = 5.0) -> WriteProbe:
    """Create a table inside a transaction and roll it back, leaving no change.

    Taking the lock alone is not enough: on a read-only file `BEGIN IMMEDIATE` still
    succeeds, because SQLite reports an error only when a page is actually written. The
    table creation forces a page write and a journal write, so it fails exactly where the
    ingestion step would fail. A lock held by another process means write access exists
    and is only busy, so it counts as a pass.

    Args:
        path: DB path to probe. Defaults to :func:`resolve_db_path`.
        timeout: Seconds to wait for the lock before concluding.

    Returns:
        Probe result with the reason.
    """
    target = Path(path) if path else resolve_db_path()
    if not target.exists():
        return WriteProbe(target, False, "không tồn tại")
    try:
        conn = sqlite3.connect(str(target), timeout=timeout, isolation_level=None)
    except sqlite3.Error as exc:
        return WriteProbe(target, False, f"không mở được: {exc}")
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("CREATE TABLE __preflight_probe (x INTEGER)")
        finally:
            conn.execute("ROLLBACK")
        return WriteProbe(target, True, "ghi được")
    except sqlite3.OperationalError as exc:
        msg = str(exc)
        if "locked" in msg or "busy" in msg:
            return WriteProbe(target, True, "ghi được, đang có tiến trình khác giữ khoá")
        return WriteProbe(target, False, msg)
    finally:
        conn.close()
