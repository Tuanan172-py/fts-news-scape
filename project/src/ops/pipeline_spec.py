"""Load the machine-readable `ops_spec` block of `.agents/pipeline.yaml` as constants for the operations code."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

PIPELINE_PATH = Path(__file__).resolve().parents[3] / ".agents" / "pipeline.yaml"
_REQUIRED = ("main_chain", "finish_steps", "script_actors", "wave_ops")


@lru_cache(maxsize=1)
def load_spec() -> dict:
    """Read the `ops_spec` block from `pipeline.yaml`.

    Returns:
        Dict with the keys main_chain, finish_steps, script_actors, wave_ops.

    Raises:
        RuntimeError: If the file, the `ops_spec` block or a required key is missing.
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
    """Return the agent order of the main chain of one wave.

    Returns:
        Agent identifiers in execution order.
    """
    return tuple(load_spec()["main_chain"])


def finish_steps() -> tuple[str, ...]:
    """Return the step order of the finish half, `article_run.py --finish`.

    Returns:
        Step names in execution order.
    """
    return tuple(load_spec()["finish_steps"])


def script_actors() -> dict[str, str]:
    """Return the mapping from script name to agent id in the registry.

    Returns:
        Dict of script name to agent id.
    """
    return dict(load_spec()["script_actors"])


def wave_ops() -> tuple[str, ...]:
    """Return the names of the steps that `WaveOps` must implement.

    Returns:
        Step method names.
    """
    return tuple(load_spec()["wave_ops"])
