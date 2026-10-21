"""Read per-user on/off switches from the single source of truth `<root>/subscriptions/manifest.yaml`."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.core import paths


def candidate_paths(input_root: str | Path | None = None) -> list[Path]:
    """List the manifest locations in priority order.

    Args:
        input_root: Explicit subscription directory; None uses the default directory.

    Returns:
        Paths: the explicit directory, `<root>/subscriptions`, then the legacy `inputs/users` layout.
    """
    out = [Path(input_root) / "manifest.yaml"] if input_root is not None else []
    out.append(paths.subscriptions_dir() / "manifest.yaml")
    out.append(paths.inputs_dir() / "users" / "manifest.yaml")
    return out


def load_user_manifest(input_root: str | Path | None = None) -> dict:
    """Load the user manifest; a name absent from `users` defaults to enabled.

    Args:
        input_root: Explicit subscription directory; None uses the default directory.

    Returns:
        Dict with `enabled` (master switch), `default` (for unlisted users) and `users` (name -> on/off).
    """
    for path in candidate_paths(input_root):
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return {
                "enabled": bool(data.get("enabled", True)),
                "default": bool(data.get("default", True)),
                "users": {str(k): bool(v) for k, v in (data.get("users") or {}).items()},
            }
    return {"enabled": True, "default": True, "users": {}}
