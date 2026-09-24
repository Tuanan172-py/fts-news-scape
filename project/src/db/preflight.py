"""Phân giải đường dẫn cơ sở dữ liệu vận hành và thử quyền ghi trước khi tiêu token."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src.core.config import load_settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_ROOT.parent


def resolve_db_path() -> Path:
    """Trả về đúng đường dẫn mà các script nạp dữ liệu sẽ ghi vào.

    Thứ tự ưu tiên trùng với `ArticleStore`: biến môi trường `MONOCLE_DB_PATH`, rồi
    `MONOCLE_DATA_DIR`, rồi `database.path` trong `settings.yaml`. Đường dẫn tương đối
    tính từ thư mục `project/`.

    Returns:
        Đường dẫn tuyệt đối tới `monocle.db`.
    """
    raw = load_settings().get("database", {}).get("path", "data/monocle.db")
    p = Path(raw)
    return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()


@dataclass
class WriteProbe:
    """Kết quả thử quyền ghi lên cơ sở dữ liệu."""

    path: Path
    ok: bool
    reason: str

    @property
    def outside_workspace(self) -> bool:
        """Cho biết tệp có nằm ngoài thư mục kho mã hay không.

        Returns:
            True khi đường dẫn không thuộc cây thư mục của kho.
        """
        try:
            self.path.resolve().relative_to(REPO_ROOT.resolve())
            return False
        except ValueError:
            return True

    def hint(self) -> str:
        """Diễn giải nguyên nhân thật của lỗi ghi thành một câu hành động được.

        Lỗi gốc của sqlite3 chỉ nói "attempt to write a readonly database", nghe như
        thuộc tính tệp bị đặt chỉ đọc, và đẩy người sửa vào hướng sai. Nguyên nhân
        thường gặp nhất trên DSH là sandbox `workspace-write` chặn ghi ra ngoài kho.

        Returns:
            Câu gợi ý, rỗng khi thử ghi thành công.
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
    """Ghi thử một bảng trong giao dịch rồi rollback, không để lại thay đổi nào.

    Chỉ giành khoá là chưa đủ: trên tệp chỉ đọc `BEGIN IMMEDIATE` vẫn thành công, vì
    SQLite chỉ báo lỗi khi thật sự ghi trang. Lệnh tạo bảng buộc ghi trang và ghi
    nhật ký giao dịch, nên nó thất bại đúng ở những chỗ bước nạp dữ liệu sẽ thất bại.
    Khoá bị tiến trình khác giữ nghĩa là quyền ghi vẫn có, chỉ đang bận, nên tính là
    đạt.

    Args:
        path: Đường dẫn DB cần thử. Mặc định lấy từ :func:`resolve_db_path`.
        timeout: Số giây chờ khoá trước khi kết luận.

    Returns:
        Kết quả thử ghi kèm lý do.
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
