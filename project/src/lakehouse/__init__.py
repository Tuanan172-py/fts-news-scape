"""Gói thư viện kiến trúc Lakehouse Data Plane phân tán trên SharePoint Sandbox."""

from __future__ import annotations

from src.lakehouse.consolidator import ConsolidationResult, consolidate_dropzone
from src.lakehouse.delivery import distribute_to_users
from src.lakehouse.ingest import publish_batch
from src.lakehouse.manifest import verify_manifest, write_manifests
from src.lakehouse.storage import (
    BaseStorageAdapter,
    GraphApiStorageAdapter,
    LocalOneDriveStorageAdapter,
)

__all__ = [
    "BaseStorageAdapter",
    "LocalOneDriveStorageAdapter",
    "GraphApiStorageAdapter",
    "publish_batch",
    "consolidate_dropzone",
    "ConsolidationResult",
    "write_manifests",
    "verify_manifest",
    "distribute_to_users",
]
