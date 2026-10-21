"""Build and store the Work Package JSON files handed to the Agent from Silver data and source metadata."""

from __future__ import annotations

from src.core import paths
import json
import os
import time

WORK_PACKAGE_SCHEMA_VERSION = "1.0"


class WorkPackageBuilder:
    """Build the structure of the work package handed to the processing agents.

    Attributes:
        schema_version: Schema version of the hand-off work package.
    """

    schema_version = WORK_PACKAGE_SCHEMA_VERSION

    def build(self, silver: dict, meta: dict, change_state: str, *,
              published_at: str | None = None, scraper_version: str = "") -> dict:
        """Package Silver data and Bronze metadata into a work package.

        Args:
            silver: Cleaned article data from the Silver layer.
            meta: Bronze capture metadata.
            change_state: Article change state ('new', 'unchanged', 'mutated').
            published_at: Article publication time in ISO 8601.
            scraper_version: Version of the source scraper.

        Returns:
            Dict with the work package structure following the work-package-v1 schema.
        """
        return {
            "schema_version": self.schema_version,
            "article_id": silver.get("article_id", ""),
            "source_url": silver.get("source_url", ""),
            "domain": silver.get("domain", ""),
            "published_at": published_at,
            "raw_html_path": meta.get("html_path", ""),
            "raw_sha256": meta.get("content_sha256", ""),
            "title": silver.get("title", ""),
            "title_verified": silver.get("title_verified", False),
            "cleaned_text": silver.get("cleaned_text", ""),
            "structure": silver.get("structure", {}),
            "images": silver.get("images", []),
            "capture_status": meta.get("capture_status", "ok"),
            "change_state": change_state,
            "provenance": {
                "fetch_ts": meta.get("fetch_ts", ""),
                "render_method": meta.get("render_method", "requests"),
                "scraper_version": scraper_version,
                "silver_schema_version": silver.get("silver_schema_version", ""),
            },
        }


def _atomic_write(path: str, data: bytes) -> None:
    """Write data to a temporary file, then swap it in atomically with retries.

    Args:
        path: Destination file path.
        data: Bytes to write.

    Raises:
        OSError: If the temporary file cannot be moved into place after all retries.
    """
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            os.replace(tmp, path)
            return
        except (PermissionError, OSError) as e:
            last_err = e
            time.sleep(0.15 * (attempt + 1))
    try:
        os.remove(tmp)
    except OSError:
        pass
    if last_err is not None:
        raise last_err


def write_package(package: dict, base_dir: str | None = None) -> str:
    """Write a work package to a JSON file on disk, grouped by domain and date.

    Args:
        package: Built work package data.
        base_dir: Base directory for work packages. Defaults to `paths.work_packages_dir()`.

    Returns:
        Absolute or relative path of the saved work package file.
    """
    domain = package.get("domain") or "unknown"
    yyyymmdd = ""
    if package.get("raw_html_path"):
        parts = package["raw_html_path"].replace("\\", "/").split("/")
        if len(parts) >= 2:
            yyyymmdd = parts[-2]
    root = paths.resolve_data_path(base_dir) if base_dir else paths.work_packages_dir()
    directory = os.path.join(str(root), domain,
                             yyyymmdd or "unknown-date")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{package['article_id']}.json")
    _atomic_write(path, json.dumps(package, ensure_ascii=False, indent=2).encode("utf-8"))
    return path
