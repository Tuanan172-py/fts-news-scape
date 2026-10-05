"""Kiểm thử các điểm ghi dữ liệu không phụ thuộc thư mục làm việc (US-035)."""

from __future__ import annotations

from pathlib import Path

from src.core.config import PROJECT_ROOT


def test_duong_dan_xuat_va_thong_bao_neo_vao_goc_du_an(tmp_path, monkeypatch):
    """Chạy ở thư mục khác không được đổi nơi ghi của export và nhật ký thông báo."""
    from src.export import csv_export, silver_manifest
    from src.notifier.file_notify import FileNotifier

    monkeypatch.chdir(tmp_path)
    assert PROJECT_ROOT in csv_export._auto_name(True, None).parents
    assert PROJECT_ROOT in silver_manifest._auto_name(True, None).parents
    assert FileNotifier().out_dir == PROJECT_ROOT / "data" / "notifications"
    assert not (tmp_path / "data").exists()


def test_ghi_goi_cong_viec_neo_vao_goc_du_an(tmp_path, monkeypatch):
    """`write_package` ghi dưới gốc dự án dù cwd ở nơi khác."""
    from src.handoff import work_package

    anchored = tmp_path / "project"
    monkeypatch.setattr(work_package, "resolve_project_path",
                        lambda p: p if Path(p).is_absolute() else anchored / p)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    path = work_package.write_package({"article_id": "a1", "domain": "cafef.vn",
                                       "raw_html_path": "data/raw_html/cafef.vn/20261005/x.html"})
    assert anchored in Path(path).parents and Path(path).exists()
    assert not (elsewhere / "data").exists()
