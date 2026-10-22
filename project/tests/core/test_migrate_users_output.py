"""Kiểm thử di chuyển tệp giao hàng sang cây users/output."""

from __future__ import annotations

from scripts.maintenance.migrate_users_output import migrate
from src.core import paths


def test_users_output_dir_is_nested(tmp_path, monkeypatch):
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(tmp_path))
    assert paths.users_output_dir() == tmp_path / "users" / "output"


def test_migrate_dry_run_then_apply(tmp_path):
    old, new = tmp_path / "users_output", tmp_path / "users" / "output"
    (old / "AnPT").mkdir(parents=True)
    (old / "_master").mkdir()
    (old / "AnPT" / "2026-10-04.xlsx").write_bytes(b"a")
    (old / "_master" / "2026-10-04.csv").write_bytes(b"m")

    rep = migrate(old, new, apply=False)
    assert rep.moved == 2 and (old / "AnPT" / "2026-10-04.xlsx").exists()
    assert not new.exists()

    rep = migrate(old, new, apply=True)
    assert rep.moved == 2 and not rep.conflicts
    assert (new / "AnPT" / "2026-10-04.xlsx").read_bytes() == b"a"
    assert not old.exists()


def test_migrate_keeps_conflicting_file(tmp_path):
    old, new = tmp_path / "users_output", tmp_path / "users" / "output"
    (old / "AnPT").mkdir(parents=True)
    (new / "AnPT").mkdir(parents=True)
    (old / "AnPT" / "d.xlsx").write_bytes(b"old")
    (new / "AnPT" / "d.xlsx").write_bytes(b"new")
    (old / "AnPT" / "same.xlsx").write_bytes(b"s")
    (new / "AnPT" / "same.xlsx").write_bytes(b"s")

    rep = migrate(old, new, apply=True)
    assert rep.conflicts == ["AnPT/d.xlsx"] and rep.identical == 1
    assert (old / "AnPT" / "d.xlsx").read_bytes() == b"old"
    assert (new / "AnPT" / "d.xlsx").read_bytes() == b"new"
    assert not (old / "AnPT" / "same.xlsx").exists()
