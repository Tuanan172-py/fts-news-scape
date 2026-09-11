"""Quản lý và tải cấu hình hệ thống, nguồn tin, danh sách theo dõi và thông tin bảo mật."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def to_project_relative(path: str | Path) -> str:
    """Chuyển đổi đường dẫn tuyệt đối thành đường dẫn tương đối so với thư mục gốc dự án.

    Args:
        path: Đường dẫn tệp hoặc thư mục cần chuyển đổi.

    Returns:
        Chuỗi đường dẫn tương đối hoặc chuỗi đường dẫn gốc nếu nằm ngoài dự án.
    """
    p = Path(path)
    try:
        return p.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def resolve_project_path(path: str | Path) -> Path:
    """Chuyển đổi đường dẫn tương đối thành đường dẫn tuyệt đối dựa trên thư mục gốc dự án.

    Args:
        path: Đường dẫn tệp hoặc thư mục dạng chuỗi hoặc Path.

    Returns:
        Đối tượng Path tuyệt đối.
    """
    p = Path(path)
    return p if p.is_absolute() else (PROJECT_ROOT / p)
CONFIG_DIR = PROJECT_ROOT / "config"
DOMAINS_DIR = CONFIG_DIR / "domains"

DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"

_DEFAULT_SETTINGS = {
    "database": {"path": str(DATA_DIR / "monocle.db")},
    "logging": {"level": "INFO", "dir": str(LOGS_DIR)},
    "scheduler": {"interval_minutes": 15},
    "http": {"rate_limit": 3.0, "timeout": 30, "max_retries": 3},
    "morninger": {
        "capture_interval_minutes": 15,
        "rederive_interval_minutes": 30,
        "drift_hour": 6,
        "drift_minute": 0,
        "drift_limit": 100,
    },
}


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings() -> dict:
    """Tải cấu hình hệ thống từ settings.yaml kết hợp giá trị mặc định và biến môi trường.

    Returns:
        Dictionary chứa toàn bộ cấu hình hoạt động của hệ thống.
    """
    cfg = _deep_merge(_DEFAULT_SETTINGS, _load_yaml(CONFIG_DIR / "settings.yaml"))

    env_data_dir = os.getenv("MONOCLE_DATA_DIR")
    env_db_path = os.getenv("MONOCLE_DB_PATH")
    if env_db_path:
        cfg.setdefault("database", {})["path"] = env_db_path
    elif env_data_dir:
        cfg.setdefault("database", {})["path"] = str(Path(env_data_dir) / "monocle.db")

    return cfg


def load_domain_config(name: str) -> dict:
    """Tải cấu hình chi tiết của một nguồn tin từ thư mục config/domains/.

    Args:
        name: Tên định danh của nguồn tin.

    Returns:
        Dictionary chứa thông số cấu hình của nguồn tin.

    Raises:
        FileNotFoundError: Khi không tìm thấy tệp cấu hình nguồn tin.
        ValueError: Khi tệp cấu hình thiếu các trường thông tin bắt buộc.
    """
    path = DOMAINS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Domain config not found: {path}")
    cfg = _load_yaml(path)
    missing = [k for k in ("name", "method") if k not in cfg]
    if missing:
        raise ValueError(f"Domain config {path} missing required keys: {missing}")
    cfg.setdefault("enabled", True)
    cfg.setdefault("rate_limit", 3.0)
    cfg.setdefault("timeout", 30)
    return cfg


def list_domains(enabled_only: bool = True) -> list[str]:
    """Liệt kê danh sách tên định danh của tất cả các nguồn tin có cấu hình.

    Args:
        enabled_only: Cờ lọc chỉ lấy các nguồn tin đang kích hoạt.

    Returns:
        Danh sách tên định danh nguồn tin đã sắp xếp.
    """
    if not DOMAINS_DIR.exists():
        return []
    names = []
    for p in sorted(DOMAINS_DIR.glob("*.yaml")):
        cfg = _load_yaml(p)
        if not enabled_only or cfg.get("enabled", True):
            names.append(p.stem)
    return names


def resolve_source_domain(name: str) -> str:
    """Xác định tên miền chính thức của nguồn tin từ tên cấu hình.

    Args:
        name: Tên định danh hoặc tên cấu hình của nguồn tin.

    Returns:
        Chuỗi tên miền đại diện cho nguồn tin trong cơ sở dữ liệu.
    """
    if not name:
        return name
    if "." in name:
        return name

    schema = PROJECT_ROOT / "domains" / name / "schema.yaml"
    domain = str((_load_yaml(schema).get("domain") or "")).strip()
    if domain:
        return domain.removeprefix("www.")

    base_url = str((_load_yaml(DOMAINS_DIR / f"{name}.yaml").get("base_url") or "")).strip()
    if base_url:
        from urllib.parse import urlparse
        netloc = urlparse(base_url).netloc.removeprefix("www.")
        if netloc:
            return netloc

    return f"{name}.vn"


def load_watchlist() -> list[str]:
    """Tải danh sách mã cổ phiếu cần theo dõi từ watchlist.yaml.

    Returns:
        Danh sách mã cổ phiếu viết hoa.
    """
    data = _load_yaml(CONFIG_DIR / "watchlist.yaml")
    return [str(t).upper() for t in data.get("tickers", [])]


def load_secrets() -> dict:
    """Tải thông tin bảo mật và API key từ secrets.yaml.

    Returns:
        Dictionary chứa các khóa và bí mật cấu hình.
    """
    return _load_yaml(CONFIG_DIR / "secrets.yaml")
