"""Kiểm thử tính chính xác, nhất quán và phát hiện giả mạo của tệp kê khai Manifest."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from src.lakehouse.consolidator import consolidate_dropzone
from src.lakehouse.ingest import publish_batch
from src.lakehouse.manifest import (
    PartitionManifestEntry,
    generate_latest_pointer_data,
    generate_manifest_data,
    verify_manifest,
    write_manifests,
)
from src.lakehouse.storage import LocalOneDriveStorageAdapter


def _create_sample_batch(count: int, date_str: str) -> list[dict]:
    """Sinh danh sách bản ghi bài viết mẫu.

    Args:
        count: Số lượng bài viết.
        date_str: Chuỗi ngày xuất bản.

    Returns:
        Danh sách các từ điển bài viết chuẩn hóa.
    """
    return [
        {
            "article_id": f"art_m_{i:03d}",
            "title": f"Bản tin tài chính kiểm định manifest {i}",
            "updated_at": f"{date_str}T10:00:00Z",
            "published_at": f"{date_str}T09:00:00Z",
            "sentiment": "pos",
            "time_sensitivity": "today",
        }
        for i in range(count)
    ]


def test_manifest_accuracy_and_pointer(tmp_path: Path):
    """Kiểm tra độ chính xác của số dòng, dung lượng tệp và mã băm SHA-256 trong manifest.

    Args:
        tmp_path: Thư mục tạm độc lập do pytest cung cấp.
    """
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
    date_str = "2026-10-08"

    records = _create_sample_batch(30, date_str)
    publish_batch(records, date_str, "dev_test", "b1", storage)
    res = consolidate_dropzone(date_str, storage)

    # 1. Kiểm tra sự tồn tại của tệp manifest theo ngày và con trỏ latest.json
    manifest_date_rel = f"_manifest/{date_str}.json"
    latest_rel = "_manifest/latest.json"
    assert storage.exists(manifest_date_rel)
    assert storage.exists(latest_rel)

    # 2. Kiểm tra tính đồng nhất nội dung giữa manifest ngày và latest.json
    manifest_data = json.loads(storage.read_bytes(manifest_date_rel).decode("utf-8"))
    latest_data = json.loads(storage.read_bytes(latest_rel).decode("utf-8"))

    assert manifest_data["date"] == date_str
    assert manifest_data["total_unique_articles"] == 30
    assert manifest_data["total_partitions"] == 1
    assert len(manifest_data["partitions"]) == 1

    part_meta = manifest_data["partitions"][0]
    assert part_meta["partition_path"] == res.partition_file
    assert part_meta["row_count"] == 30

    # Đối chiếu mã băm và dung lượng tính trực tiếp từ tệp Parquet
    part_bytes = storage.read_bytes(res.partition_file)
    actual_sha = hashlib.sha256(part_bytes).hexdigest()
    actual_size = len(part_bytes)

    assert part_meta["sha256"] == actual_sha
    assert part_meta["size_bytes"] == actual_size
    assert res.sha256 == actual_sha

    # 3. Kiểm tra con trỏ latest.json
    assert latest_data["latest_date"] == date_str
    assert latest_data["manifest_ref"] == manifest_date_rel
    assert latest_data["total_unique_articles"] == 30
    assert len(latest_data["files"]) == 1

    latest_file_meta = latest_data["files"][0]
    assert latest_file_meta["path"] == res.partition_file
    assert latest_file_meta["rows"] == 30
    assert latest_file_meta["size_bytes"] == actual_size
    assert latest_file_meta["sha256"] == actual_sha

    # 4. Kiểm chứng tính toàn vẹn qua hàm verify_manifest
    report_date = verify_manifest(manifest_date_rel, storage)
    assert report_date["valid"] is True
    assert report_date["total_partitions"] == 1
    assert report_date["total_rows"] == 30
    assert len(report_date["mismatches"]) == 0

    report_latest = verify_manifest(latest_rel, storage)
    assert report_latest["valid"] is True
    assert report_latest["total_partitions"] == 1
    assert report_latest["total_rows"] == 30
    assert len(report_latest["mismatches"]) == 0


def test_manifest_tamper_detection_byte_mutation(tmp_path: Path):
    """Kiểm tra khả năng phát hiện khi tệp Parquet bị sửa đổi một phần nội dung byte.

    Args:
        tmp_path: Thư mục tạm độc lập do pytest cung cấp.
    """
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
    date_str = "2026-10-08"

    records = _create_sample_batch(10, date_str)
    publish_batch(records, date_str, "dev_test", "b1", storage)
    res = consolidate_dropzone(date_str, storage)

    # Ban đầu kiểm chứng thành công
    rep1 = verify_manifest("_manifest/latest.json", storage)
    assert rep1["valid"] is True

    # Sửa đổi 1 byte trong tệp Parquet thành phẩm
    part_loc = storage.get_local_path(res.partition_file)
    assert part_loc is not None
    original_data = bytearray(part_loc.read_bytes())
    original_data[10] = (original_data[10] + 1) % 256
    part_loc.write_bytes(bytes(original_data))

    # Kiểm chứng lại: phải phát hiện sai lệch mã băm SHA-256
    rep2 = verify_manifest("_manifest/latest.json", storage)
    assert rep2["valid"] is False
    assert any("Lệch mã băm SHA-256" in m for m in rep2["mismatches"])


def test_manifest_tamper_detection_missing_file(tmp_path: Path):
    """Kiểm tra khả năng phát hiện khi tệp phân vùng bị xóa mất khỏi đĩa.

    Args:
        tmp_path: Thư mục tạm độc lập do pytest cung cấp.
    """
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
    date_str = "2026-10-08"

    records = _create_sample_batch(5, date_str)
    publish_batch(records, date_str, "dev_test", "b1", storage)
    res = consolidate_dropzone(date_str, storage)

    # Xóa tệp phân vùng Parquet
    storage.delete(res.partition_file)

    report = verify_manifest("_manifest/latest.json", storage)
    assert report["valid"] is False
    assert any("Tệp không tồn tại" in m for m in report["mismatches"])


def test_verify_manifest_missing_manifest_file(tmp_path: Path):
    """Kiểm tra ngoại lệ FileNotFoundError khi đường dẫn tệp manifest không tồn tại.

    Args:
        tmp_path: Thư mục tạm độc lập do pytest cung cấp.
    """
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
    with pytest.raises(FileNotFoundError, match="Không tìm thấy tệp manifest"):
        verify_manifest("_manifest/non_existent.json", storage)


def test_write_manifests_direct_unit(tmp_path: Path):
    """Kiểm tra trực tiếp hàm sinh tệp kê khai write_manifests với nhiều phân vùng.

    Args:
        tmp_path: Thư mục tạm độc lập do pytest cung cấp.
    """
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
    date_str = "2026-10-08"

    # Tạo 2 tệp giả lập
    p1 = "parquet/articles/year=2026/month=10/part-1.parquet"
    p2 = "parquet/articles/year=2026/month=10/part-2.parquet"
    data1 = b"parquet_data_1"
    data2 = b"parquet_data_2"
    storage.write_atomic(p1, data1)
    storage.write_atomic(p2, data2)

    entries = [
        PartitionManifestEntry(
            partition_path=p1,
            row_count=100,
            size_bytes=len(data1),
            sha256=hashlib.sha256(data1).hexdigest(),
            year="2026",
            month="10",
            date="20261008",
        ),
        PartitionManifestEntry(
            partition_path=p2,
            row_count=150,
            size_bytes=len(data2),
            sha256=hashlib.sha256(data2).hexdigest(),
            year="2026",
            month="10",
            date="20261008",
        ),
    ]

    saved_manifest, saved_latest = write_manifests(
        date_str=date_str,
        partitions=entries,
        storage=storage,
    )

    assert saved_manifest == f"_manifest/{date_str}.json"
    assert saved_latest == "_manifest/latest.json"

    report = verify_manifest(saved_manifest, storage)
    assert report["valid"] is True
    assert report["total_partitions"] == 2
    assert report["total_rows"] == 250
    assert len(report["mismatches"]) == 0
