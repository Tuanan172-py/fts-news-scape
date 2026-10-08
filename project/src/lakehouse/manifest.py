"""Quản lý tệp kê khai toàn vẹn dữ liệu Manifest cho kiến trúc Lakehouse."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.lakehouse.storage import BaseStorageAdapter


@dataclass
class PartitionManifestEntry:
    """Thông tin chi tiết của một phân vùng dữ liệu Parquet.

    Attributes:
        partition_path: Đường dẫn tương đối của tệp tin phân vùng Parquet.
        row_count: Tổng số dòng bài viết trong phân vùng.
        size_bytes: Kích thước tệp tin tính theo byte.
        sha256: Mã băm SHA-256 của tệp tin Parquet thành phẩm.
        year: Năm phân vùng.
        month: Tháng phân vùng.
        date: Chuỗi ngày phân vùng dạng YYYYMMDD.
    """

    partition_path: str
    row_count: int
    size_bytes: int
    sha256: str
    year: str
    month: str
    date: str

    def to_dict(self) -> dict[str, Any]:
        """Chuyển đổi thực thể thành từ điển dữ liệu.

        Returns:
            Từ điển chứa toàn bộ thuộc tính của phân vùng.
        """
        return asdict(self)


def generate_manifest_data(
    date_str: str,
    partitions: list[PartitionManifestEntry],
    engine_name: str = "DuckDB",
) -> dict[str, Any]:
    """Sinh cấu trúc dữ liệu kê khai toàn vẹn theo chuẩn Lakehouse Manifest.

    Args:
        date_str: Ngày nghiệp vụ của tệp kê khai (YYYY-MM-DD hoặc YYYYMMDD).
        partitions: Danh sách các phân vùng dữ liệu Parquet.
        engine_name: Tên động cơ xử lý dữ liệu.

    Returns:
        Từ điển dữ liệu tệp kê khai hoàn chỉnh.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    total_records = sum(p.row_count for p in partitions)

    return {
        "$schema": "https://fra.local/schemas/lakehouse-manifest-v1.json",
        "version": "1.0.0",
        "date": date_str,
        "generated_at": now_iso,
        "total_unique_articles": total_records,
        "total_partitions": len(partitions),
        "partitions": [p.to_dict() for p in partitions],
        "engine_metadata": {
            "engine": engine_name,
            "compression": "ZSTD",
        },
    }


def generate_latest_pointer_data(
    date_str: str,
    manifest_ref: str,
    partitions: list[PartitionManifestEntry],
) -> dict[str, Any]:
    """Sinh dữ liệu con trỏ latest.json trỏ tới bản kê khai mới nhất.

    Args:
        date_str: Ngày nghiệp vụ của bản kê khai.
        manifest_ref: Đường dẫn tham chiếu tới tệp kê khai theo ngày.
        partitions: Danh sách các phân vùng dữ liệu.

    Returns:
        Từ điển dữ liệu con trỏ latest.json.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    total_records = sum(p.row_count for p in partitions)

    return {
        "latest_date": date_str,
        "manifest_ref": manifest_ref,
        "updated_at": now_iso,
        "total_unique_articles": total_records,
        "total_partitions": len(partitions),
        "files": [
            {
                "path": p.partition_path,
                "rows": p.row_count,
                "size_bytes": p.size_bytes,
                "sha256": p.sha256,
            }
            for p in partitions
        ],
    }


def write_manifests(
    date_str: str,
    partitions: list[PartitionManifestEntry],
    storage: BaseStorageAdapter,
    manifest_dir: str = "_manifest",
    engine_name: str = "DuckDB",
) -> tuple[str, str]:
    """Ghi tệp kê khai theo ngày và cập nhật con trỏ latest.json nguyên tử ra kho lưu trữ.

    Args:
        date_str: Chuỗi ngày nghiệp vụ (vd: '2026-10-08').
        partitions: Danh sách các phân vùng Parquet thành phẩm.
        storage: Adapter giao tiếp hệ thống lưu trữ.
        manifest_dir: Thư mục chứa các tệp kê khai (mặc định '_manifest').
        engine_name: Tên động cơ xử lý dữ liệu.

    Returns:
        Tuple gồm (đường dẫn tệp manifest theo ngày, đường dẫn tệp latest.json).
    """
    clean_date = date_str.replace("/", "-")
    manifest_rel_path = f"{manifest_dir}/{clean_date}.json"
    latest_rel_path = f"{manifest_dir}/latest.json"

    manifest_payload = generate_manifest_data(
        date_str=clean_date,
        partitions=partitions,
        engine_name=engine_name,
    )
    latest_payload = generate_latest_pointer_data(
        date_str=clean_date,
        manifest_ref=manifest_rel_path,
        partitions=partitions,
    )

    manifest_bytes = json.dumps(manifest_payload, indent=2, ensure_ascii=False).encode("utf-8")
    latest_bytes = json.dumps(latest_payload, indent=2, ensure_ascii=False).encode("utf-8")

    saved_manifest = storage.write_atomic(manifest_rel_path, manifest_bytes)
    saved_latest = storage.write_atomic(latest_rel_path, latest_bytes)

    return saved_manifest, saved_latest


def verify_manifest(
    manifest_path: str,
    storage: BaseStorageAdapter,
) -> dict[str, Any]:
    """Kiểm chứng tính toàn vẹn của tệp manifest đối chiếu với dữ liệu thực tế.

    Args:
        manifest_path: Đường dẫn tệp manifest cần kiểm định (vd: '_manifest/latest.json').
        storage: Adapter giao tiếp hệ thống lưu trữ.

    Returns:
        Từ điển kết quả thẩm định gồm trạng thái hợp lệ, số phân vùng và các lỗi phát hiện.

    Raises:
        FileNotFoundError: Khi tệp manifest không tồn tại.
    """
    if not storage.exists(manifest_path):
        raise FileNotFoundError(f"Không tìm thấy tệp manifest tại: {manifest_path}")

    raw_bytes = storage.read_bytes(manifest_path)
    manifest_data = json.loads(raw_bytes.decode("utf-8"))

    mismatches: list[str] = []
    total_rows = 0

    # Xử lý cả định dạng manifest ngày và định dạng con trỏ latest.json
    partitions_list = manifest_data.get("partitions") or manifest_data.get("files") or []

    for item in partitions_list:
        file_path = item.get("partition_path") or item.get("path")
        expected_sha = item.get("sha256")
        expected_size = item.get("size_bytes")
        rows = item.get("row_count") or item.get("rows") or 0
        total_rows += rows

        if not storage.exists(file_path):
            mismatches.append(f"Tệp không tồn tại: {file_path}")
            continue

        actual_bytes = storage.read_bytes(file_path)
        actual_size = len(actual_bytes)
        actual_sha = hashlib.sha256(actual_bytes).hexdigest()

        if expected_size is not None and actual_size != expected_size:
            mismatches.append(
                f"Lệch kích thước tệp {file_path}: kỳ vọng {expected_size}, thực tế {actual_size}"
            )
        if expected_sha and actual_sha != expected_sha:
            mismatches.append(
                f"Lệch mã băm SHA-256 tệp {file_path}: kỳ vọng {expected_sha}, thực tế {actual_sha}"
            )

    is_valid = len(mismatches) == 0

    return {
        "valid": is_valid,
        "manifest_path": manifest_path,
        "total_partitions": len(partitions_list),
        "total_rows": total_rows,
        "mismatches": mismatches,
    }
