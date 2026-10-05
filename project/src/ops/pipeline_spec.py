"""Nạp khối máy đọc `ops_spec` của `.agents/pipeline.yaml` thành hằng số cho mã vận hành."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

PIPELINE_PATH = Path(__file__).resolve().parents[3] / ".agents" / "pipeline.yaml"
_REQUIRED = ("main_chain", "finish_steps", "script_actors", "wave_ops")


@lru_cache(maxsize=1)
def load_spec() -> dict:
    """Đọc khối `ops_spec` từ `pipeline.yaml`.

    Returns:
        Từ điển có các khoá main_chain, finish_steps, script_actors, wave_ops.

    Raises:
        RuntimeError: Khi thiếu tệp, thiếu khối `ops_spec` hoặc thiếu khoá bắt buộc.
    """
    try:
        data = yaml.safe_load(PIPELINE_PATH.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise RuntimeError(f"Không đọc được {PIPELINE_PATH}: {exc}") from exc
    spec = data.get("ops_spec")
    if not isinstance(spec, dict):
        raise RuntimeError("pipeline.yaml thiếu khối ops_spec")
    missing = [k for k in _REQUIRED if k not in spec]
    if missing:
        raise RuntimeError(f"ops_spec thiếu khoá: {', '.join(missing)}")
    return spec


def main_chain() -> tuple[str, ...]:
    """Trả về thứ tự tác nhân của dây chuyền chính một đợt."""
    return tuple(load_spec()["main_chain"])


def finish_steps() -> tuple[str, ...]:
    """Trả về thứ tự các bước của nửa hoàn tất `article_run.py --finish`."""
    return tuple(load_spec()["finish_steps"])


def script_actors() -> dict[str, str]:
    """Trả về bảng tên script sang id tác nhân trong registry."""
    return dict(load_spec()["script_actors"])


def wave_ops() -> tuple[str, ...]:
    """Trả về tên các bước mà `WaveOps` phải hiện thực."""
    return tuple(load_spec()["wave_ops"])
