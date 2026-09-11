"""Bộ xây dựng và lưu trữ gói công việc (Work Package) bàn giao cho Agent.

Cung cấp lớp WorkPackageBuilder và hàm ghi tệp an toàn để đóng gói dữ liệu Silver
kèm siêu dữ liệu nguồn thành tệp tin JSON tự mô tả.
"""

from __future__ import annotations

import json
import os

WORK_PACKAGE_SCHEMA_VERSION = "1.0"


class WorkPackageBuilder:
    """Bộ khởi tạo cấu trúc gói công việc bàn giao cho các agent xử lý.

    Attributes:
        schema_version: Phiên bản lược đồ của gói công việc bàn giao.
    """

    schema_version = WORK_PACKAGE_SCHEMA_VERSION

    def build(self, silver: dict, meta: dict, change_state: str, *,
              published_at: str | None = None, scraper_version: str = "") -> dict:
        """Đóng gói dữ liệu tầng Silver và metadata tầng Bronze thành gói công việc.

        Args:
            silver: Dữ liệu bài viết đã xử lý sạch tầng Silver.
            meta: Siêu dữ liệu thu thập tầng Bronze (metadata capture).
            change_state: Trạng thái thay đổi bài viết ('new', 'unchanged', 'mutated').
            published_at: Thời điểm xuất bản bài viết theo chuẩn ISO 8601.
            scraper_version: Phiên bản của bộ thu thập dữ liệu nguồn.

        Returns:
            Từ điển chứa cấu trúc gói công việc theo lược đồ work-package-v1.
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
    """Ghi dữ liệu ra tệp tạm thời rồi hoán đổi nguyên tử (atomic swap)."""
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def write_package(package: dict, base_dir: str = "data/work_packages") -> str:
    """Lưu gói công việc ra tệp tin JSON trên đĩa theo phân cấp tên miền và ngày tháng.

    Args:
        package: Dữ liệu gói công việc đã khởi tạo.
        base_dir: Thư mục cơ sở lưu trữ các gói công việc.

    Returns:
        Đường dẫn tuyệt đối hoặc tương đối tới tệp tin gói công việc đã lưu.
    """
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
