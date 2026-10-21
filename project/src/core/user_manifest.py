"""Đọc công tắc bật/tắt người dùng từ nguồn chân lý duy nhất `<gốc>/subscriptions/manifest.yaml`."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.core import paths


def candidate_paths(input_root: str | Path | None = None) -> list[Path]:
    """Liệt kê các vị trí manifest theo thứ tự ưu tiên.

    Args:
        input_root: Thư mục đăng ký chỉ định rõ; None dùng thư mục mặc định.

    Returns:
        Danh sách đường dẫn: thư mục chỉ định, `<gốc>/subscriptions`, bố cục cũ `inputs/users`.
    """
    out = [Path(input_root) / "manifest.yaml"] if input_root is not None else []
    out.append(paths.subscriptions_dir() / "manifest.yaml")
    out.append(paths.inputs_dir() / "users" / "manifest.yaml")
    return out


def load_user_manifest(input_root: str | Path | None = None) -> dict:
    """Tải manifest người dùng; vắng tên trong `users` mặc định BẬT.

    Args:
        input_root: Thư mục đăng ký chỉ định rõ; None dùng thư mục mặc định.

    Returns:
        Từ điển `enabled` (công tắc tổng), `default` (cho người chưa liệt kê), `users` (tên -> bật/tắt).
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
