"""Resolve every operational data path from the single root `data_root()`, taken from `MONOCLE_DATA_DIR` (default `C:\\data\\news-scape`) with the subscriptions directory from `NEWS_SCAPE_SUBSCRIPTIONS_DIR`."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

DATA_DIR_ENV = "MONOCLE_DATA_DIR"
SUBSCRIPTIONS_DIR_ENV = "NEWS_SCAPE_SUBSCRIPTIONS_DIR"
DEFAULT_DATA_ROOT = Path(r"C:\data\news-scape")

# Prefixes of legacy relative paths, from when data lived under `project/data`.
_LEGACY_PREFIXES = ("project/data/", "data/")


class UnsafeDataRootError(RuntimeError):
    """Raised when the operational data root falls in a OneDrive or SharePoint synced folder."""


def check_data_root(root: Path) -> Path:
    """Reject a data root located in a cloud-synced area.

    Args:
        root: Data root to check.

    Returns:
        The same data root when valid.

    Raises:
        UnsafeDataRootError: If the path contains `onedrive` or `sharepoint`.
    """
    low = str(root).lower()
    if "onedrive" in low or "sharepoint" in low:
        raise UnsafeDataRootError(
            f"Thư mục dữ liệu vận hành {root} nằm trong OneDrive/SharePoint. "
            f"Đặt {DATA_DIR_ENV} về ổ cục bộ, mặc định {DEFAULT_DATA_ROOT}."
        )
    return root


def data_root() -> Path:
    """Return the operational data root, re-reading the environment variable on every call.

    Returns:
        Absolute path of the data root.

    Raises:
        UnsafeDataRootError: If the data root is in OneDrive or SharePoint.
    """
    raw = os.environ.get(DATA_DIR_ENV) or str(DEFAULT_DATA_ROOT)
    return check_data_root(Path(raw).expanduser().absolute())


def _sub(*parts: str) -> Path:
    """Join a subdirectory under the data root.

    Args:
        *parts: Relative path components.

    Returns:
        Absolute path under the data root.
    """
    return data_root().joinpath(*parts)


def db_path() -> Path:
    """Return the default path of `monocle.db` under the data root.

    Returns:
        Absolute path to the operational DB.
    """
    return _sub("monocle.db")


def bronze_dir() -> Path:
    """Return the Bronze directory holding raw HTML and `.meta.json`.

    Returns:
        Path `<root>/raw_html`.
    """
    return _sub("raw_html")


def raw_reports_dir() -> Path:
    """Return the Bronze directory of periodic reports.

    Returns:
        Path `<root>/raw_reports`.
    """
    return _sub("raw_reports")


def silver_dir() -> Path:
    """Return the Silver JSON directory.

    Returns:
        Path `<root>/silver`.
    """
    return _sub("silver")


def work_packages_dir() -> Path:
    """Return the work-package directory.

    Returns:
        Path `<root>/work_packages`.
    """
    return _sub("work_packages")


def agent_tasks_dir() -> Path:
    """Return the root directory of packets handed to agents.

    Returns:
        Path `<root>/agent_tasks`.
    """
    return _sub("agent_tasks")


def article_packets_dir() -> Path:
    """Return the packet and batch-manifest directory of the Article Lane.

    Returns:
        Path `<root>/agent_tasks/article`.
    """
    return agent_tasks_dir() / "article"


def agent_outputs_dir(kind: str = "") -> Path:
    """Return the agent output directory for a kind suffix.

    Args:
        kind: Directory name suffix, for example `""`, `"_l1"`, `"_article"`.

    Returns:
        Path `<root>/agent_outputs<kind>`.
    """
    return _sub(f"agent_outputs{kind}")


def article_mentions_dir() -> Path:
    """Return the directory of per-article entity mention records.

    Returns:
        Path `<root>/article_mentions`.
    """
    return _sub("article_mentions")


def state_dir() -> Path:
    """Return the directory of hand-off state between sessions.

    Returns:
        Path `<root>/state`.
    """
    return _sub("state")


def exports_dir() -> Path:
    """Return the CSV export directory.

    Returns:
        Path `<root>/exports`.
    """
    return _sub("exports")


def notifications_dir() -> Path:
    """Return the file-based notification directory.

    Returns:
        Path `<root>/notifications`.
    """
    return _sub("notifications")


def reports_dir() -> Path:
    """Return the operational report directory.

    Returns:
        Path `<root>/reports`.
    """
    return _sub("reports")


def entities_dir() -> Path:
    """Return the directory of generated entity catalogs (`entities.json`, `taxonomy.json`, CSV).

    Returns:
        Path `<root>/entities`.
    """
    return _sub("entities")


def logs_dir() -> Path:
    """Return the application log directory.

    Returns:
        Path `<root>/logs`.
    """
    return _sub("logs")


def users_output_dir() -> Path:
    """Return the per-user delivery directory.

    Returns:
        Path `<root>/users/output`, the same tree as SharePoint (ADR-0026.D6).
    """
    return _sub("users", "output")


def subscriptions_dir() -> Path:
    """Return the user subscription directory.

    Returns:
        The `NEWS_SCAPE_SUBSCRIPTIONS_DIR` value if set, otherwise `<root>/subscriptions`.
    """
    raw = os.environ.get(SUBSCRIPTIONS_DIR_ENV)
    return Path(raw).expanduser().absolute() if raw else _sub("subscriptions")


def snapshots_dir() -> Path:
    """Return the directory of DB snapshots kept for review.

    Returns:
        Path `<root>/snapshots`.
    """
    return _sub("snapshots")


def staging_dir() -> Path:
    """Return the buffer directory of the atomic file write mechanism.

    Returns:
        Path `<root>/staging`.
    """
    return _sub("staging")


def publish_staging_dir() -> Path:
    """Return the directory where complete files are built before publishing (ADR 0020 §2.3).

    Returns:
        Path `<root>/publish_staging`.
    """
    return _sub("publish_staging")


def inputs_dir() -> Path:
    """Return the directory of input copies edited by people (ADR 0020 §2.4).

    Returns:
        Path `<root>/inputs`.
    """
    return _sub("inputs")


def to_data_relative(path: str | Path) -> str:
    """Convert a path under the data root to a relative path with forward slashes.

    Args:
        path: Absolute or relative path.

    Returns:
        Path relative to the data root if the file is inside it, otherwise the string unchanged.
    """
    p = Path(path)
    if not p.is_absolute():
        return str(path).replace("\\", "/")
    try:
        return p.absolute().relative_to(data_root()).as_posix()
    except ValueError:
        return str(path)


def strip_legacy_prefix(stored: str) -> str:
    """Strip the `data/` or `project/data/` prefix of a legacy relative path.

    Args:
        stored: Relative path as stored.

    Returns:
        Path relative to the data root, with forward slashes.
    """
    s = stored.replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    for prefix in _LEGACY_PREFIXES:
        if s.startswith(prefix):
            return s[len(prefix):]
    return s


def resolve_data_path(stored: str | Path) -> Path:
    """Resolve a persisted path to an absolute path under the data root.

    Accepts three forms: absolute (kept as is), new-style relative (`raw_html/...`) and
    legacy relative with a `data/` or `project/data/` prefix.

    Args:
        stored: Path read from the DB, a meta file or a manifest.

    Returns:
        Absolute path.
    """
    p = Path(stored)
    if p.is_absolute():
        return p
    rel = strip_legacy_prefix(str(stored))
    return data_root().joinpath(*PurePosixPath(rel).parts)
