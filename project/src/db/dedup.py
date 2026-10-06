"""Kiểm tra bài đã thấy bằng mã băm chính xác và ghi sổ phát hiện URL."""

from __future__ import annotations

import json
import os
import re
import time

from loguru import logger

from src.core import paths
from src.core.models import normalize_title, sha256_hash
from src.db import registry
from src.db.store import ArticleStore

_LEGACY_JSON = str(paths.data_root() / "dedup_cache.json")


class DedupCache:
    """Bộ nhớ đệm kiểm tra chống trùng lặp dựa trên bảng seen_articles trong SQLite.

    Attributes:
        store: Đối tượng ArticleStore quản lý cơ sở dữ liệu.
    """

    def __init__(self, store: ArticleStore, legacy_json_path: str = _LEGACY_JSON):
        self.store = store
        self._conn = store._connect()
        self._migrate_legacy_json(legacy_json_path)

    def _migrate_legacy_json(self, path: str) -> None:
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                hashes: dict[str, float] = json.load(f)
            self._conn.executemany(
                "INSERT OR IGNORE INTO seen_articles (hash, title_norm, source_domain, seen_at) "
                "VALUES (?, '', 'legacy', ?)",
                [(h, ts) for h, ts in hashes.items()],
            )
            self._conn.commit()
            os.remove(path)
            logger.info("Migrated {} legacy dedup hashes from {} (file removed)",
                        len(hashes), path)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Legacy dedup migration skipped ({}): {}", path, e)

    def is_duplicate(self, url: str, title: str) -> bool:
        """Kiểm tra bài viết đã từng xuất hiện qua mã băm SHA-256(url + title).

        Args:
            url: Đường dẫn bài viết.
            title: Tiêu đề bài viết.

        Returns:
            True nếu bài viết đã tồn tại trong bộ nhớ đệm.
        """
        h = sha256_hash(url, title)
        row = self._conn.execute(
            "SELECT 1 FROM seen_articles WHERE hash=?", (h,)).fetchone()
        return row is not None

    def mark_seen(self, url: str, title: str, source_domain: str = "") -> None:
        """Đánh dấu bài viết đã được ghi nhận vào bộ nhớ đệm chống trùng.

        Args:
            url: Đường dẫn bài viết.
            title: Tiêu đề bài viết.
            source_domain: Tên miền nguồn tin.
        """
        self._conn.execute(
            "INSERT OR IGNORE INTO seen_articles (hash, title_norm, source_domain, seen_at) "
            "VALUES (?, ?, ?, ?)",
            (sha256_hash(url, title), normalize_title(title), source_domain, time.time()),
        )
        self._conn.commit()

    def discover(self, url: str, source_domain: str, via: str = "listing") -> tuple[str, bool, bool]:
        """Ghi URL vào sổ phát hiện trước mọi bước lọc.

        Args:
            url: URL như nguồn trả về.
            source_domain: Tên miền nguồn.
            via: Kênh phát hiện: listing, rss, api, sitemap hoặc reconcile.

        Returns:
            Bộ (khoá bài, là bài mới, là dạng URL khác dạng đã thấy đầu tiên).
        """
        res = registry.discover(self._conn, url, source_domain, via)
        self._conn.commit()
        return res

    def is_captured(self, key: str) -> bool:
        """Kiểm tra bài mang khoá này đã được lưu thành bài trong kho hay chưa.

        Args:
            key: Khoá bài từ `src.core.urlnorm.url_key`.

        Returns:
            True nếu sổ phát hiện ghi trạng thái captured.
        """
        return registry.is_captured(self._conn, key)

    def known_keys(self, keys: list[str]) -> set[str]:
        """Lọc ra các khoá bài đã được lưu thành bài trong kho.

        Args:
            keys: Danh sách khoá bài cần tra.

        Returns:
            Tập khoá đã ở trạng thái captured, dùng làm mốc dừng phân trang.
        """
        return registry.known_keys(self._conn, keys)

    def cleanup(self, max_age_days: int = 30) -> int:
        """Xóa các bản ghi đã xem cũ hơn số ngày quy định.

        Args:
            max_age_days: Số ngày lưu giữ tối đa.

        Returns:
            Số bản ghi đã bị xóa bỏ.
        """
        cutoff = time.time() - max_age_days * 86400
        cur = self._conn.execute("DELETE FROM seen_articles WHERE seen_at < ?", (cutoff,))
        self._conn.commit()
        return cur.rowcount

    def count(self) -> int:
        """Đếm tổng số bản ghi đã ghi nhận trong bảng seen_articles.

        Returns:
            Số lượng bản ghi trong bảng.
        """
        return self._conn.execute("SELECT COUNT(*) FROM seen_articles").fetchone()[0]

    def close(self) -> None:
        """Đóng kết nối cơ sở dữ liệu của bộ nhớ đệm."""
        self._conn.close()
