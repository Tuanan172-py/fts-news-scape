"""Phân giải mọi đường dẫn dữ liệu vận hành từ một gốc duy nhất `data_root()`.

- Gốc dữ liệu: biến môi trường `MONOCLE_DATA_DIR`, mặc định `C:\\data\\news-scape`.
- Thư mục đăng ký người dùng: `NEWS_SCAPE_SUBSCRIPTIONS_DIR`, mặc định `<gốc>/subscriptions`.
- Đường dẫn lưu bền (DB, meta Bronze, manifest đợt) ghi tương đối theo gốc dữ liệu.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

DATA_DIR_ENV = "MONOCLE_DATA_DIR"
SUBSCRIPTIONS_DIR_ENV = "NEWS_SCAPE_SUBSCRIPTIONS_DIR"
DEFAULT_DATA_ROOT = Path(r"C:\data\news-scape")

# Tiền tố của đường dẫn tương đối kiểu cũ, khi dữ liệu còn nằm dưới `project/data`.
_LEGACY_PREFIXES = ("project/data/", "data/")


class UnsafeDataRootError(RuntimeError):
    """Báo gốc dữ liệu vận hành rơi vào thư mục đồng bộ OneDrive hoặc SharePoint."""


def check_data_root(root: Path) -> Path:
    """Từ chối gốc dữ liệu nằm trong vùng đồng bộ đám mây.

    Args:
        root: Gốc dữ liệu cần kiểm.

    Returns:
        Chính gốc dữ liệu khi hợp lệ.

    Raises:
        UnsafeDataRootError: Khi đường dẫn chứa `onedrive` hoặc `sharepoint`.
    """
    low = str(root).lower()
    if "onedrive" in low or "sharepoint" in low:
        raise UnsafeDataRootError(
            f"Thư mục dữ liệu vận hành {root} nằm trong OneDrive/SharePoint. "
            f"Đặt {DATA_DIR_ENV} về ổ cục bộ, mặc định {DEFAULT_DATA_ROOT}."
        )
    return root


def data_root() -> Path:
    """Trả về gốc dữ liệu vận hành, đọc lại biến môi trường ở mỗi lần gọi.

    Returns:
        Đường dẫn tuyệt đối của gốc dữ liệu.

    Raises:
        UnsafeDataRootError: Khi gốc dữ liệu nằm trong OneDrive hoặc SharePoint.
    """
    raw = os.environ.get(DATA_DIR_ENV) or str(DEFAULT_DATA_ROOT)
    return check_data_root(Path(raw).expanduser().absolute())


def _sub(*parts: str) -> Path:
    """Ghép thư mục con dưới gốc dữ liệu.

    Args:
        *parts: Các thành phần đường dẫn tương đối.

    Returns:
        Đường dẫn tuyệt đối dưới gốc dữ liệu.
    """
    return data_root().joinpath(*parts)


def db_path() -> Path:
    """Trả về đường dẫn mặc định của `monocle.db` dưới gốc dữ liệu.

    Returns:
        Đường dẫn tuyệt đối tới DB vận hành.
    """
    return _sub("monocle.db")


def bronze_dir() -> Path:
    """Trả về thư mục Bronze chứa HTML thô và `.meta.json`.

    Returns:
        Đường dẫn `<gốc>/raw_html`.
    """
    return _sub("raw_html")


def raw_reports_dir() -> Path:
    """Trả về thư mục Bronze của báo cáo định kỳ.

    Returns:
        Đường dẫn `<gốc>/raw_reports`.
    """
    return _sub("raw_reports")


def silver_dir() -> Path:
    """Trả về thư mục Silver JSON.

    Returns:
        Đường dẫn `<gốc>/silver`.
    """
    return _sub("silver")


def work_packages_dir() -> Path:
    """Trả về thư mục work-package.

    Returns:
        Đường dẫn `<gốc>/work_packages`.
    """
    return _sub("work_packages")


def agent_tasks_dir() -> Path:
    """Trả về thư mục gốc của packet giao cho tác nhân.

    Returns:
        Đường dẫn `<gốc>/agent_tasks`.
    """
    return _sub("agent_tasks")


def article_packets_dir() -> Path:
    """Trả về thư mục packet và manifest đợt của Article Lane.

    Returns:
        Đường dẫn `<gốc>/agent_tasks/article`.
    """
    return agent_tasks_dir() / "article"


def agent_outputs_dir(kind: str = "") -> Path:
    """Trả về thư mục đầu ra của tác nhân theo hậu tố loại.

    Args:
        kind: Hậu tố tên thư mục, ví dụ `""`, `"_l1"`, `"_article"`.

    Returns:
        Đường dẫn `<gốc>/agent_outputs<kind>`.
    """
    return _sub(f"agent_outputs{kind}")


def article_mentions_dir() -> Path:
    """Trả về thư mục bản ghi nhắc thực thể theo bài.

    Returns:
        Đường dẫn `<gốc>/article_mentions`.
    """
    return _sub("article_mentions")


def state_dir() -> Path:
    """Trả về thư mục trạng thái bàn giao giữa các phiên.

    Returns:
        Đường dẫn `<gốc>/state`.
    """
    return _sub("state")


def exports_dir() -> Path:
    """Trả về thư mục tệp xuất CSV.

    Returns:
        Đường dẫn `<gốc>/exports`.
    """
    return _sub("exports")


def notifications_dir() -> Path:
    """Trả về thư mục thông báo dạng tệp.

    Returns:
        Đường dẫn `<gốc>/notifications`.
    """
    return _sub("notifications")


def reports_dir() -> Path:
    """Trả về thư mục báo cáo vận hành.

    Returns:
        Đường dẫn `<gốc>/reports`.
    """
    return _sub("reports")


def entities_dir() -> Path:
    """Trả về thư mục danh mục thực thể sinh ra (`entities.json`, `taxonomy.json`, CSV).

    Returns:
        Đường dẫn `<gốc>/entities`.
    """
    return _sub("entities")


def logs_dir() -> Path:
    """Trả về thư mục nhật ký ứng dụng.

    Returns:
        Đường dẫn `<gốc>/logs`.
    """
    return _sub("logs")


def users_output_dir() -> Path:
    """Trả về thư mục giao hàng theo người dùng.

    Returns:
        Đường dẫn `<gốc>/users_output`.
    """
    return _sub("users_output")


def subscriptions_dir() -> Path:
    """Trả về thư mục đăng ký của người dùng.

    Returns:
        Giá trị `NEWS_SCAPE_SUBSCRIPTIONS_DIR` khi có, ngược lại `<gốc>/subscriptions`.
    """
    raw = os.environ.get(SUBSCRIPTIONS_DIR_ENV)
    return Path(raw).expanduser().absolute() if raw else _sub("subscriptions")


def snapshots_dir() -> Path:
    """Trả về thư mục bản chụp DB để rà soát.

    Returns:
        Đường dẫn `<gốc>/snapshots`.
    """
    return _sub("snapshots")


def staging_dir() -> Path:
    """Trả về thư mục đệm của cơ chế ghi tệp nguyên tử.

    Returns:
        Đường dẫn `<gốc>/staging`.
    """
    return _sub("staging")


def publish_staging_dir() -> Path:
    """Trả về thư mục dựng tệp hoàn chỉnh trước khi xuất bản (ADR 0020 §2.3).

    Returns:
        Đường dẫn `<gốc>/publish_staging`.
    """
    return _sub("publish_staging")


def inputs_dir() -> Path:
    """Trả về thư mục bản chép đầu vào do người sửa (ADR 0020 §2.4).

    Returns:
        Đường dẫn `<gốc>/inputs`.
    """
    return _sub("inputs")


def to_data_relative(path: str | Path) -> str:
    """Đưa đường dẫn dưới gốc dữ liệu về dạng tương đối dấu gạch chéo xuôi.

    Args:
        path: Đường dẫn tuyệt đối hoặc tương đối.

    Returns:
        Chuỗi tương đối theo gốc dữ liệu khi tệp nằm trong đó, ngược lại giữ nguyên chuỗi.
    """
    p = Path(path)
    if not p.is_absolute():
        return str(path).replace("\\", "/")
    try:
        return p.absolute().relative_to(data_root()).as_posix()
    except ValueError:
        return str(path)


def strip_legacy_prefix(stored: str) -> str:
    """Bỏ tiền tố `data/` hoặc `project/data/` của đường dẫn tương đối kiểu cũ.

    Args:
        stored: Đường dẫn tương đối như đã lưu.

    Returns:
        Đường dẫn tương đối theo gốc dữ liệu, dấu gạch chéo xuôi.
    """
    s = stored.replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    for prefix in _LEGACY_PREFIXES:
        if s.startswith(prefix):
            return s[len(prefix):]
    return s


def resolve_data_path(stored: str | Path) -> Path:
    """Phân giải đường dẫn đã lưu bền thành đường dẫn tuyệt đối dưới gốc dữ liệu.

    Chấp nhận ba dạng: tuyệt đối (giữ nguyên), tương đối kiểu mới (`raw_html/...`) và
    tương đối kiểu cũ có tiền tố `data/` hoặc `project/data/`.

    Args:
        stored: Đường dẫn đọc từ DB, tệp meta hoặc manifest.

    Returns:
        Đường dẫn tuyệt đối.
    """
    p = Path(stored)
    if p.is_absolute():
        return p
    rel = strip_legacy_prefix(str(stored))
    return data_root().joinpath(*PurePosixPath(rel).parts)
