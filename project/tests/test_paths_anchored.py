"""Kiểm thử các điểm ghi dữ liệu không phụ thuộc thư mục làm việc (US-035, US-038)."""

from __future__ import annotations

from pathlib import Path


def test_duong_dan_xuat_va_thong_bao_neo_vao_goc_du_lieu(tmp_path, monkeypatch):
    """Chạy ở thư mục khác không được đổi nơi ghi của export và nhật ký thông báo."""
    from src.export import csv_export, silver_manifest
    from src.notifier.file_notify import FileNotifier

    root = tmp_path / "root"
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(root))
    monkeypatch.chdir(tmp_path)
    assert root / "exports" == csv_export._auto_name(True, None).parent
    assert root / "exports" == silver_manifest._auto_name(True, None).parent
    assert FileNotifier().out_dir == root / "notifications"
    assert not (tmp_path / "data").exists()


def test_ghi_goi_cong_viec_neo_vao_goc_du_lieu(tmp_path, monkeypatch):
    """`write_package` ghi dưới gốc dữ liệu dù cwd ở nơi khác."""
    from src.handoff import work_package

    root = tmp_path / "root"
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(root))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    path = work_package.write_package({"article_id": "a1", "domain": "cafef.vn",
                                       "raw_html_path": "raw_html/cafef.vn/20261005/x.html"})
    assert Path(path).parent == root / "work_packages" / "cafef.vn" / "20261005"
    assert Path(path).exists()
    assert not (elsewhere / "data").exists()
