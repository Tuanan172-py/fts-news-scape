"""Load configuration, paths and secrets for the autonomous operations layer."""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.core import paths as data_paths
from src.core.paths import PROJECT_ROOT

CONFIG_PATH = PROJECT_ROOT / "config" / "ops.yaml"

DEFAULTS: dict[str, Any] = {
    "sensor": {"interval_seconds": 120, "threshold": 100, "max_age_minutes": 90,
               "age_rule_hours": [6, 22],
               "flush_windows": ["07:15-07:45", "12:15-12:45", "15:15-15:45", "17:15-17:45"],
               "lookback_days": 1},
    "wave": {"runner": "agy", "limit": 100, "batch": 50, "concurrency": 2,
             "max_repair_rounds": 2, "max_attempts_per_article": 2, "cooldown_minutes": 30,
             "progress_silence_minutes": 25, "min_free_gb": 5,
             "deadlines_minutes": {"preflight": 2, "prepare": 5, "analyze": 45,
                                   "repair": 25, "finish": 30}},
    "autonomy": {"demote_after_failures": 2, "max_order_days": 30, "renew_when_days_left": 7,
                 "renew_min_clean_streak": 5},
    "control_room": {"enabled": True, "port": 8787},
    "improvement": {"max_per_week": 5},
    "watchdog": {"stale_minutes": 10},
    "breaker": {"timeout_trip": 3, "timeout_open_minutes": 30, "network_trip": 3,
                "network_open_minutes": 10, "empty_trip": 2, "quota_open_minutes": 300},
    "heartbeat": {"interval_seconds": 60},
    "digest": {"times": ["08:00", "18:00"]},
    "supervisor": {"manage_capture": True, "restart_backoff_seconds": [10, 30, 60, 120, 300],
                   "max_restarts": 5, "restart_window_minutes": 30},
    "probes": {"capture_stale_minutes": 30, "capture_hours": [7, 22],
               "dead_letter_alert_delta": 50},
    "alerts": {"dedup_minutes": 30, "push_wave_info": False},
    "telegram": {"poll_timeout_seconds": 25},
}


def _merge(base: dict, override: dict) -> dict:
    """Merge two dicts recursively, with `override` values taking precedence.

    Args:
        base: Base dict.
        override: Overriding dict.

    Returns:
        New merged dict.
    """
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Read `config/ops.yaml` and merge it with the defaults.

    Args:
        path: Configuration file path. Defaults to the project `config/ops.yaml`.

    Returns:
        Full configuration dict.
    """
    p = Path(path) if path else CONFIG_PATH
    data: dict[str, Any] = {}
    if p.exists():
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return _merge(DEFAULTS, data)


@dataclass(frozen=True)
class OpsPaths:
    """Set of operations paths, all located outside OneDrive.

    Attributes:
        data_dir: Operations data directory.
        ops_db: Database of events, alerts, breakers and state.
        dbos_db: DBOS system database (workflow checkpoints).
        log_dir: Directory of JSONL logs and per-step logs.
        kill_switch: Emergency stop flag file.
        pipeline_lock: Single-process lock file shared with `article_tick.py`.
        daemon_lock: Lock file that keeps the daemon to one instance.
        standing_order: File holding the time-limited operations mandate.
        secrets_file: Secrets file in KEY=VALUE format.
        harness_db: `harness.db`, which receives per-agent KPIs (`agent_metrics`).
    """

    data_dir: Path
    ops_db: Path
    dbos_db: Path
    log_dir: Path
    kill_switch: Path
    pipeline_lock: Path
    daemon_lock: Path
    standing_order: Path
    secrets_file: Path
    harness_db: Path


def resolve_paths(data_dir: Path | None = None) -> OpsPaths:
    """Build the operations paths from `MONOCLE_DATA_DIR` or a given directory.

    Args:
        data_dir: Data directory. Defaults to `src.core.paths.data_root()`.

    Returns:
        The OpsPaths object.

    Raises:
        RuntimeError: If the data directory is inside OneDrive or SharePoint.
    """
    d = data_paths.check_data_root(Path(data_dir)) if data_dir else data_paths.data_root()
    return OpsPaths(
        data_dir=d,
        ops_db=d / "ops.db",
        dbos_db=d / "ops_dbos.db",
        log_dir=d / "ops_logs",
        kill_switch=d / "AGY_STOP",
        pipeline_lock=d / ".pipeline.lock",
        daemon_lock=d / "ops_daemon.lock",
        standing_order=d / "agy_standing_order.yaml",
        secrets_file=d / "secrets" / "ops.env",
        # An explicitly given directory (tests) receives the KPIs, leaving the real DB untouched.
        harness_db=(PROJECT_ROOT.parent / "harness.db") if data_dir is None else d / "harness.db",
    )


def load_secrets(paths: OpsPaths) -> dict[str, str]:
    """Read secrets from `secrets/ops.env`, with environment variables taking precedence.

    Keys in use: `NEWS_SCAPE_TG_TOKEN`, `NEWS_SCAPE_TG_CHAT_IDS` (comma-separated),
    `NEWS_SCAPE_HC_URL`.

    Args:
        paths: Operations paths.

    Returns:
        Secrets dict, possibly empty.
    """
    out: dict[str, str] = {}
    if paths.secrets_file.exists():
        for line in paths.secrets_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip("'\"")
    for key in ("NEWS_SCAPE_TG_TOKEN", "NEWS_SCAPE_TG_CHAT_IDS", "NEWS_SCAPE_HC_URL"):
        if os.environ.get(key):
            out[key] = os.environ[key]
    return out


def write_secret(paths: OpsPaths, key: str, value: str) -> None:
    """Write or replace one key in the secrets file.

    Args:
        paths: Operations paths.
        key: Key name.
        value: Key value.
    """
    paths.secrets_file.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if paths.secrets_file.exists():
        lines = [ln for ln in paths.secrets_file.read_text(encoding="utf-8").splitlines()
                 if not ln.strip().startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    paths.secrets_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
