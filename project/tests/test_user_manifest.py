"""Kiểm thử nguồn chân lý duy nhất bật/tắt người dùng (ADR-0026.D5)."""

from __future__ import annotations

from src.core.user_manifest import load_user_manifest


def test_manifest_read_from_subscriptions_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_SCAPE_SUBSCRIPTIONS_DIR", str(tmp_path))
    (tmp_path / "manifest.yaml").write_text("users:\n  A: true\n  B: false\n", encoding="utf-8")
    m = load_user_manifest()
    assert m["users"] == {"A": True, "B": False} and m["default"] is True and m["enabled"] is True


def test_manifest_missing_means_everyone_on(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_SCAPE_SUBSCRIPTIONS_DIR", str(tmp_path / "none"))
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(tmp_path))
    assert load_user_manifest() == {"enabled": True, "default": True, "users": {}}


def test_global_switch_off(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_SCAPE_SUBSCRIPTIONS_DIR", str(tmp_path))
    (tmp_path / "manifest.yaml").write_text("enabled: false\nusers:\n  A: true\n", encoding="utf-8")
    assert load_user_manifest()["enabled"] is False
