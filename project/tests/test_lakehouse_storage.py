"""Bộ kiểm thử đơn vị cho tầng trừu tượng lưu trữ Storage Adapter."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.lakehouse.storage import (
    BaseStorageAdapter,
    GraphApiStorageAdapter,
    LocalOneDriveStorageAdapter,
)


def test_local_onedrive_storage_basic_io() -> None:
    """Kiểm tra các thao tác đọc ghi cơ bản trên LocalOneDriveStorageAdapter."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        adapter = LocalOneDriveStorageAdapter(tmp_dir)

        test_rel = "dropzone/2026/10/08/test.txt"
        test_data = b"Lakehouse Storage Test Data"

        # Kiểm tra trạng thái tồn tại trước khi ghi
        assert not adapter.exists(test_rel)

        # Ghi nguyên tử
        saved_path = adapter.write_atomic(test_rel, test_data)
        assert saved_path == test_rel
        assert adapter.exists(test_rel)

        # Đọc dữ liệu
        read_back = adapter.read_bytes(test_rel)
        assert read_back == test_data

        # Kiểm tra đường dẫn cục bộ
        local_p = adapter.get_local_path(test_rel)
        assert local_p is not None
        assert local_p.is_file()
        assert local_p.read_bytes() == test_data


def test_local_onedrive_storage_list_files_filtering() -> None:
    """Kiểm tra việc lọc danh sách tệp và bỏ qua các tệp tạm thời .partial và .tmp."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        adapter = LocalOneDriveStorageAdapter(tmp_dir)

        # Tạo một số tệp hợp lệ và tệp tạm
        adapter.write_atomic("dropzone/2026/10/08/part-1.parquet", b"part1")
        adapter.write_atomic("dropzone/2026/10/08/part-2.parquet", b"part2")

        # Tạo thủ công tệp .partial và .tmp
        root = Path(tmp_dir)
        (root / "dropzone/2026/10/08/part-3.parquet.partial").write_bytes(b"partial")
        (root / "dropzone/2026/10/08/part-4.parquet.tmp").write_bytes(b"tmp")

        matched = adapter.list_files("dropzone/*/*/*/*.parquet")
        assert len(matched) == 2
        assert "dropzone/2026/10/08/part-1.parquet" in matched
        assert "dropzone/2026/10/08/part-2.parquet" in matched


def test_local_onedrive_storage_delete() -> None:
    """Kiểm tra chức năng xóa tệp tin khỏi kho lưu trữ."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        adapter = LocalOneDriveStorageAdapter(tmp_dir)
        test_path = "temp/delete_me.bin"
        adapter.write_atomic(test_path, b"to be deleted")

        assert adapter.exists(test_path)
        deleted = adapter.delete(test_path)
        assert deleted is True
        assert not adapter.exists(test_path)

        # Xóa lần nữa trả về False
        assert adapter.delete(test_path) is False


def test_local_onedrive_storage_idempotent_write() -> None:
    """Kiểm tra cơ chế ghi lặp byte-level không gây lỗi khi dữ liệu không đổi."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        adapter = LocalOneDriveStorageAdapter(tmp_dir)
        path = "data/static.bin"
        payload = b"idempotent content"

        p1 = adapter.write_atomic(path, payload)
        p2 = adapter.write_atomic(path, payload)
        assert p1 == p2
        assert adapter.read_bytes(path) == payload


def test_graph_api_storage_stub_raises() -> None:
    """Kiểm tra GraphApiStorageAdapter ném NotImplementedError theo đúng hợp đồng."""
    adapter = GraphApiStorageAdapter(
        tenant_id="test-tenant",
        client_id="test-client",
        client_secret="test-secret",
        drive_id="test-drive",
    )

    with pytest.raises(NotImplementedError):
        adapter.list_files("*")

    with pytest.raises(NotImplementedError):
        adapter.read_bytes("path/to/file")

    with pytest.raises(NotImplementedError):
        adapter.write_atomic("path/to/file", b"data")

    with pytest.raises(NotImplementedError):
        adapter.exists("path/to/file")

    assert adapter.get_local_path("path/to/file") is None
