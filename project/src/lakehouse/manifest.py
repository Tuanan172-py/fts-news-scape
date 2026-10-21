"""Manage the integrity manifest files of the Lakehouse architecture."""

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
    """Details of one Parquet data partition.

    Attributes:
        partition_path: Relative path of the Parquet partition file.
        row_count: Total number of article rows in the partition.
        size_bytes: File size in bytes.
        sha256: SHA-256 hash of the resulting Parquet file.
        year: Partition year.
        month: Partition month.
        date: Partition date string as YYYYMMDD.
    """

    partition_path: str
    row_count: int
    size_bytes: int
    sha256: str
    year: str
    month: str
    date: str

    def to_dict(self) -> dict[str, Any]:
        """Convert the entry to a data dict.

        Returns:
            Dict with all attributes of the partition.
        """
        return asdict(self)


def generate_manifest_data(
    date_str: str,
    partitions: list[PartitionManifestEntry],
    engine_name: str = "DuckDB",
) -> dict[str, Any]:
    """Build the integrity manifest data structure of the Lakehouse Manifest standard.

    Args:
        date_str: Business date of the manifest (YYYY-MM-DD or YYYYMMDD).
        partitions: Parquet data partitions.
        engine_name: Name of the data processing engine.

    Returns:
        Complete manifest data dict.
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
    """Build the latest.json pointer data that points to the newest manifest.

    Args:
        date_str: Business date of the manifest.
        manifest_ref: Reference path of the daily manifest file.
        partitions: Data partitions.

    Returns:
        Pointer data dict for latest.json.
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
    """Write the daily manifest and update the latest.json pointer atomically in storage.

    Args:
        date_str: Business date string (for example '2026-10-08').
        partitions: Resulting Parquet partitions.
        storage: Storage system adapter.
        manifest_dir: Directory that holds the manifest files.
        engine_name: Name of the data processing engine.

    Returns:
        Tuple of (daily manifest path, latest.json path).
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
    """Verify the integrity of a manifest file against the actual data.

    Args:
        manifest_path: Path of the manifest to verify (for example '_manifest/latest.json').
        storage: Storage system adapter.

    Returns:
        Result dict with the validity flag, partition count and the mismatches found.

    Raises:
        FileNotFoundError: If the manifest file does not exist.
    """
    if not storage.exists(manifest_path):
        raise FileNotFoundError(f"Không tìm thấy tệp manifest tại: {manifest_path}")

    raw_bytes = storage.read_bytes(manifest_path)
    manifest_data = json.loads(raw_bytes.decode("utf-8"))

    mismatches: list[str] = []
    total_rows = 0

    # Handle both the daily manifest format and the latest.json pointer format.
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
