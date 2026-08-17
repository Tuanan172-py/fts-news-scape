"""
WorkPackageBuilder — gói 1 bài thành work-package (INPUT contract cho agent).

Self-describing, provider-agnostic JSON. TRỎ tới Bronze raw (raw_html_path+raw_sha256),
KHÔNG inline bytes → agent re-verify offline. Xem phase-03, schemas/work-package-v1.
"""

from __future__ import annotations

import json
import os

WORK_PACKAGE_SCHEMA_VERSION = "1.0"


class WorkPackageBuilder:
    schema_version = WORK_PACKAGE_SCHEMA_VERSION

    def build(self, silver: dict, meta: dict, change_state: str, *,
              published_at: str | None = None, scraper_version: str = "") -> dict:
        return {
            "schema_version": self.schema_version,
            "article_id": silver.get("article_id", ""),
            "source_url": silver.get("source_url", ""),
            "domain": silver.get("domain", ""),
            "published_at": published_at,
            "raw_html_path": meta.get("html_path", ""),
            "raw_sha256": meta.get("content_sha256", ""),
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
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def write_package(package: dict, base_dir: str = "data/work_packages") -> str:
    domain = package.get("domain") or "unknown"
    yyyymmdd = ""
    if package.get("raw_html_path"):
        parts = package["raw_html_path"].replace("\\", "/").split("/")
        if len(parts) >= 2:
            yyyymmdd = parts[-2]
    directory = os.path.join(base_dir, domain, yyyymmdd or "unknown-date")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{package['article_id']}.json")
    _atomic_write(path, json.dumps(package, ensure_ascii=False, indent=2).encode("utf-8"))
    return path
