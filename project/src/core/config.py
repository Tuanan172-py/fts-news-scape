"""Load system settings, source configs, the watchlist and secrets."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from src.core import paths
from src.core.paths import PROJECT_ROOT, REPO_ROOT


CONFIG_DIR = PROJECT_ROOT / "config"
DOMAINS_DIR = CONFIG_DIR / "domains"


OPERATIONAL_DB_PATH = paths.DEFAULT_DATA_ROOT / "monocle.db"
ALLOW_SYNCED_DB_ENV = "MONOCLE_ALLOW_SYNCED_DB"

_DEFAULT_SETTINGS = {
    "database": {},
    "logging": {"level": "INFO"},
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
    """Load system settings from settings.yaml merged with defaults and environment variables.

    Returns:
        Dict with the full runtime configuration.
    """
    cfg = _deep_merge(_DEFAULT_SETTINGS, _load_yaml(CONFIG_DIR / "settings.yaml"))

    env_data_dir = os.getenv(paths.DATA_DIR_ENV)
    env_db_path = os.getenv("MONOCLE_DB_PATH")
    if env_db_path:
        cfg.setdefault("database", {})["path"] = env_db_path
    elif env_data_dir:
        cfg.setdefault("database", {})["path"] = str(paths.db_path())

    cfg.setdefault("database", {})["path"] = str(resolve_db_path(cfg))
    log_dir = (cfg.get("logging") or {}).get("dir")
    cfg.setdefault("logging", {})["dir"] = str(
        paths.resolve_data_path(log_dir) if log_dir else paths.logs_dir())
    return cfg


class UnsafeDatabasePathError(RuntimeError):
    """Raised when the operational DB path falls in a cloud-synced folder or the code repository."""


def is_synced_location(path: Path) -> bool:
    """Check whether a path lies in OneDrive or in the code repository tree.

    SQLite in WAL mode keeps three files (`.db`, `-wal`, `-shm`). OneDrive syncs them out
    of step and creates per-machine conflict copies, and a process missing the environment
    variable would write to a stale copy instead of the operational DB.

    Args:
        path: Absolute path to check.

    Returns:
        True if the path is in a synced area or in the code repository.
    """
    if any(part.lower().startswith("onedrive") for part in path.parts):
        return True
    try:
        path.relative_to(REPO_ROOT.resolve())
        return True
    except ValueError:
        return False


def resolve_db_path(settings: dict | None = None) -> Path:
    """Resolve the absolute path of the operational DB and reject unsafe locations.

    Priority order: `MONOCLE_DB_PATH`, then `MONOCLE_DATA_DIR`, then `database.path` in
    `settings.yaml`, and finally `monocle.db` under `paths.data_root()`. A relative path
    is taken from the `project/` directory, not from the cwd.

    Args:
        settings: Loaded settings; None loads them.

    Returns:
        Absolute path to `monocle.db`.

    Raises:
        UnsafeDatabasePathError: If the path is in OneDrive or the code repository and
            `MONOCLE_ALLOW_SYNCED_DB` is not set.
    """
    cfg = settings if settings is not None else load_settings()
    raw = (cfg.get("database") or {}).get("path") or str(paths.db_path())
    p = Path(raw)
    p = (p if p.is_absolute() else PROJECT_ROOT / p).resolve()
    if is_synced_location(p) and not os.getenv(ALLOW_SYNCED_DB_ENV):
        raise UnsafeDatabasePathError(
            f"DB vận hành trỏ vào {p}, nằm trong OneDrive hoặc kho mã. Đặt biến môi "
            f"trường MONOCLE_DB_PATH={OPERATIONAL_DB_PATH} hoặc sửa database.path trong "
            f"config/settings.yaml. Chỉ đặt {ALLOW_SYNCED_DB_ENV}=1 khi cố ý mở bản sao cũ."
        )
    return p


def load_domain_config(name: str) -> dict:
    """Load the detailed config of one source from the config/domains/ directory.

    Args:
        name: Source name.

    Returns:
        Dict of the source configuration parameters.

    Raises:
        FileNotFoundError: If the source config file is not found.
        ValueError: If the config file lacks required keys.
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
    """List the names of all configured sources.

    Args:
        enabled_only: If True, return only enabled sources.

    Returns:
        Sorted source names.
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
    """Resolve the official domain of a source from its config name.

    Args:
        name: Source name or config name.

    Returns:
        Domain that represents the source in the database.
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
    """Load the watched stock tickers from watchlist.yaml.

    Returns:
        Uppercase tickers.
    """
    data = _load_yaml(CONFIG_DIR / "watchlist.yaml")
    return [str(t).upper() for t in data.get("tickers", [])]


def load_secrets() -> dict:
    """Load secrets and API keys from secrets.yaml.

    Returns:
        Dict of configured keys and secrets.
    """
    return _load_yaml(CONFIG_DIR / "secrets.yaml")
