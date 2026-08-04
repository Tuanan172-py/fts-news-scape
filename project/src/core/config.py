"""
Config loaders — settings, per-domain, watchlist, secrets.

Config-driven (spec §12): thêm domain mới = thêm file YAML trong
config/domains/ + module scraper, không sửa core.
"""

from __future__ import annotations

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DOMAINS_DIR = CONFIG_DIR / "domains"

_DEFAULT_SETTINGS = {
    "database": {"path": "data/monocle.db"},
    "logging": {"level": "INFO", "dir": "logs"},
    "scheduler": {"interval_minutes": 15},
    "http": {"rate_limit": 3.0, "timeout": 30, "max_retries": 3},
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
    """config/settings.yaml merge lên defaults."""
    return _deep_merge(_DEFAULT_SETTINGS, _load_yaml(CONFIG_DIR / "settings.yaml"))


def load_domain_config(name: str) -> dict:
    """Load config/domains/<name>.yaml. Raise rõ ràng nếu thiếu file/key bắt buộc."""
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
    """Tên tất cả domain có config (sắp xếp ổn định)."""
    if not DOMAINS_DIR.exists():
        return []
    names = []
    for p in sorted(DOMAINS_DIR.glob("*.yaml")):
        cfg = _load_yaml(p)
        if not enabled_only or cfg.get("enabled", True):
            names.append(p.stem)
    return names


def load_watchlist() -> list[str]:
    """Danh sách mã cổ phiếu theo dõi (uppercase)."""
    data = _load_yaml(CONFIG_DIR / "watchlist.yaml")
    return [str(t).upper() for t in data.get("tickers", [])]


def load_secrets() -> dict:
    """config/secrets.yaml (gitignored). Trả {} nếu chưa có."""
    return _load_yaml(CONFIG_DIR / "secrets.yaml")
