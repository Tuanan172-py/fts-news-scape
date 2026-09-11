"""Kiểm tra và xử lý chống trùng lặp bài viết (mã băm chính xác và so khớp mờ)."""

from __future__ import annotations

import json
import os
import re
import time

from loguru import logger

from src.core.models import normalize_title, sha256_hash
from src.db.store import ArticleStore

_LEGACY_JSON = "data/dedup_cache.json"


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

    def recent_titles(self, hours: float = 48.0,
                      exclude_domain: str = "") -> list[tuple[str, str]]:
        """Lấy danh sách tiêu đề chuẩn hóa gần đây từ các nguồn khác để đối chiếu mờ.

        Args:
            hours: Khoảng thời gian quét tính bằng giờ.
            exclude_domain: Tên miền cần loại trừ không so sánh.

        Returns:
            Danh sách bộ (tiêu đề chuẩn hóa, tên miền).
        """
        cutoff = time.time() - hours * 3600
        rows = self._conn.execute(
            "SELECT title_norm, source_domain FROM seen_articles "
            "WHERE seen_at > ? AND source_domain != ? AND title_norm != ''",
            (cutoff, exclude_domain)).fetchall()
        return [(r["title_norm"], r["source_domain"]) for r in rows]

    def is_similar_title(self, title: str, source_domain: str,
                         hours: float = 48.0, threshold: int = 90) -> bool:
        """Đối chiếu độ tương đồng tiêu đề bài viết giữa các nguồn tin khác nhau.

        Args:
            title: Tiêu đề bài viết cần kiểm tra.
            source_domain: Tên miền của bài viết hiện tại.
            hours: Khoảng thời gian quét đối chiếu tính bằng giờ.
            threshold: Ngưỡng điểm tương đồng tối thiểu (0-100).

        Returns:
            True nếu phát hiện tiêu đề trùng lặp ngữ nghĩa vượt ngưỡng.
        """
        from rapidfuzz import fuzz

        norm = normalize_title(title)
        if not norm:
            return False
        for candidate, dom in self.recent_titles(hours, exclude_domain=source_domain):
            if fuzz.token_set_ratio(norm, candidate) >= threshold:
                logger.debug("Fuzzy dup: '{}' ~ '{}' ({})", norm[:50], candidate[:50], dom)
                return True
        return False

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
