"""Nạp cấu hình, đường dẫn và bí mật cho tầng vận hành tự chủ."""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "ops.yaml"

DEFAULTS: dict[str, Any] = {
    "sensor": {"interval_seconds": 120, "threshold": 100, "max_age_minutes": 90,
               "age_rule_hours": [6, 22],
               "flush_windows": ["07:15-07:45", "12:15-12:45", "15:15-15:45", "17:15-17:45"],
               "lookback_days": 1},
    "wave": {"runner": "agy", "limit": 100, "batch": 50, "concurrency": 2,
             "max_repair_rounds": 2, "max_attempts_per_article": 2,
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
    """Trộn đệ quy hai từ điển, giá trị của `override` thắng.

    Args:
        base: Từ điển gốc.
        override: Từ điển ghi đè.

    Returns:
        Từ điển mới đã trộn.
    """
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Đọc `config/ops.yaml` và trộn với giá trị mặc định.

    Args:
        path: Đường dẫn tệp cấu hình. Mặc định là `config/ops.yaml` của dự án.

    Returns:
        Từ điển cấu hình đầy đủ.
    """
    p = Path(path) if path else CONFIG_PATH
    data: dict[str, Any] = {}
    if p.exists():
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return _merge(DEFAULTS, data)


@dataclass(frozen=True)
class OpsPaths:
    """Tập đường dẫn vận hành, đều nằm ngoài OneDrive.

    Attributes:
        data_dir: Thư mục dữ liệu vận hành.
        ops_db: DB sự kiện, cảnh báo, breaker và trạng thái.
        dbos_db: DB hệ thống của DBOS (checkpoint workflow).
        log_dir: Thư mục nhật ký JSONL và log từng bước.
        kill_switch: Tệp cờ dừng khẩn cấp.
        pipeline_lock: Tệp khoá đơn tiến trình dùng chung với `article_tick.py`.
        daemon_lock: Tệp khoá một thể hiện của daemon.
        standing_order: Tệp chỉ lệnh uỷ quyền vận hành có thời hạn.
        secrets_file: Tệp bí mật dạng KEY=VALUE.
        harness_db: `harness.db` nhận KPI từng tác nhân (`agent_metrics`).
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
    """Dựng tập đường dẫn vận hành từ `MONOCLE_DATA_DIR` hoặc thư mục chỉ định.

    Args:
        data_dir: Thư mục dữ liệu. Mặc định `C:\\data\\news-scape`.

    Returns:
        Đối tượng OpsPaths.

    Raises:
        RuntimeError: Khi thư mục dữ liệu nằm trong OneDrive hoặc SharePoint.
    """
    d = Path(data_dir or os.environ.get("MONOCLE_DATA_DIR", r"C:\data\news-scape"))
    low = str(d).lower()
    if "onedrive" in low or "sharepoint" in low:
        raise RuntimeError(f"Thư mục dữ liệu vận hành {d} nằm trong OneDrive/SharePoint.")
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
        # Thư mục chỉ định tường minh (kiểm thử) thì KPI ghi vào đó, không đụng DB thật.
        harness_db=(PROJECT_ROOT.parent / "harness.db") if data_dir is None else d / "harness.db",
    )


def load_secrets(paths: OpsPaths) -> dict[str, str]:
    """Đọc bí mật từ tệp `secrets/ops.env`, biến môi trường ghi đè.

    Khoá được dùng: `NEWS_SCAPE_TG_TOKEN`, `NEWS_SCAPE_TG_CHAT_IDS` (phân tách bằng dấu
    phẩy), `NEWS_SCAPE_HC_URL`.

    Args:
        paths: Tập đường dẫn vận hành.

    Returns:
        Từ điển bí mật, có thể rỗng.
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
    """Ghi hoặc thay một khoá trong tệp bí mật.

    Args:
        paths: Tập đường dẫn vận hành.
        key: Tên khoá.
        value: Giá trị.
    """
    paths.secrets_file.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if paths.secrets_file.exists():
        lines = [ln for ln in paths.secrets_file.read_text(encoding="utf-8").splitlines()
                 if not ln.strip().startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    paths.secrets_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
