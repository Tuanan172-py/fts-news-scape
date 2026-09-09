"""
Config loaders — settings, per-domain, watchlist, secrets.

Config-driven (spec §12): thêm domain mới = thêm file YAML trong
config/domains/ + module scraper, không sửa core.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def to_project_relative(path: str | Path) -> str:
    """Duong dan LUU VAO DB phai tuong doi theo PROJECT_ROOT.

    Luu duong dan tuyet doi khien du lieu dinh chat vao mot may: monocle.db dang co 1.364
    dong `C:/Users/anpt/...` va 423 dong `C:/Users/An Thanh Pham/...` — may nao cung chi mo
    duoc phan cua minh. Ngoai PROJECT_ROOT thi giu nguyen (khong ep ../.. kho doc).
    """
    p = Path(path)
    try:
        return p.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def resolve_project_path(path: str | Path) -> Path:
    """Nghich dao cua to_project_relative: doc duoc ca ban tuong doi lan ban tuyet doi cu."""
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
    """config/settings.yaml merge lên defaults + hỗ trợ override từ biến môi trường."""
    cfg = _deep_merge(_DEFAULT_SETTINGS, _load_yaml(CONFIG_DIR / "settings.yaml"))

    # Hỗ trợ override đường dẫn data ra ngoài OneDrive qua MONOCLE_DATA_DIR hoặc MONOCLE_DB_PATH
    env_data_dir = os.getenv("MONOCLE_DATA_DIR")
    env_db_path = os.getenv("MONOCLE_DB_PATH")
    if env_db_path:
        cfg.setdefault("database", {})["path"] = env_db_path
    elif env_data_dir:
        cfg.setdefault("database", {})["path"] = str(Path(env_data_dir) / "monocle.db")

    return cfg


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


def resolve_source_domain(name: str) -> str:
    """Tên config → host thật dùng trong `articles.source_domain`.

    Thứ tự ưu tiên:
      1. Đã có dấu chấm → coi như host, trả nguyên (vd "cafef.vn").
      2. `domain:` trong domains/<name>/schema.yaml — contract thật của nguồn.
      3. `config/domains/<name>.yaml` → base_url netloc (bỏ "www.").
      4. Fallback legacy `<name>.vn` (giữ tương thích ngược cho caller cũ).

    Sửa bẫy cũ `f"{dom}.vn" if "." not in dom else dom`: tên config KHÔNG phải lúc
    nào cũng là host stem — vd `tnck` → `tinnhanhchungkhoan.vn`, không phải `tnck.vn`.
    Bẫy này làm domain_check/domain_reporter query nhầm và báo "0 articles".
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
    """Danh sách mã cổ phiếu theo dõi (uppercase)."""
    data = _load_yaml(CONFIG_DIR / "watchlist.yaml")
    return [str(t).upper() for t in data.get("tickers", [])]


def load_secrets() -> dict:
    """config/secrets.yaml (gitignored). Trả {} nếu chưa có."""
    return _load_yaml(CONFIG_DIR / "secrets.yaml")
