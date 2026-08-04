"""
Deduplication — lớp 1: SHA-256(url+title), backed bởi bảng seen_articles
trong cùng SQLite DB (WAL-safe, thay JSON file cũ).

title_norm được lưu kèm cho lớp 2 (fuzzy match cross-domain — Phase 4).
Migration 1 lần từ data/dedup_cache.json nếu còn tồn tại.
"""

from __future__ import annotations

import json
import os
import re
import time

from loguru import logger

from src.core.models import sha256_hash
from src.db.store import ArticleStore

_LEGACY_JSON = "data/dedup_cache.json"


def normalize_title(title: str) -> str:
    """Lowercase + gộp whitespace, giữ dấu tiếng Việt (input cho fuzzy Phase 4)."""
    return re.sub(r"\s+", " ", title.strip().lower())


class DedupCache:
    """Dedup backed bởi SQLite. Mỗi instance giữ 1 connection (dùng trong 1 thread)."""

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
        h = sha256_hash(url, title)
        row = self._conn.execute(
            "SELECT 1 FROM seen_articles WHERE hash=?", (h,)).fetchone()
        return row is not None

    def mark_seen(self, url: str, title: str, source_domain: str = "") -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO seen_articles (hash, title_norm, source_domain, seen_at) "
            "VALUES (?, ?, ?, ?)",
            (sha256_hash(url, title), normalize_title(title), source_domain, time.time()),
        )
        self._conn.commit()

    def recent_titles(self, hours: float = 48.0,
                      exclude_domain: str = "") -> list[tuple[str, str]]:
        """(title_norm, source_domain) trong N giờ gần nhất — cho fuzzy Phase 4."""
        cutoff = time.time() - hours * 3600
        rows = self._conn.execute(
            "SELECT title_norm, source_domain FROM seen_articles "
            "WHERE seen_at > ? AND source_domain != ? AND title_norm != ''",
            (cutoff, exclude_domain)).fetchall()
        return [(r["title_norm"], r["source_domain"]) for r in rows]

    def is_similar_title(self, title: str, source_domain: str,
                         hours: float = 48.0, threshold: int = 90) -> bool:
        """Lớp 2: fuzzy match title cross-domain (cùng bài đăng lại nguồn khác).

        Same-domain đã xử lý bởi lớp hash; chỉ so với domain KHÁC trong window.
        token_set_ratio chịu được đảo mệnh đề (tin VN hay xáo thứ tự).
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
        cutoff = time.time() - max_age_days * 86400
        cur = self._conn.execute("DELETE FROM seen_articles WHERE seen_at < ?", (cutoff,))
        self._conn.commit()
        return cur.rowcount

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM seen_articles").fetchone()[0]

    def close(self) -> None:
        self._conn.close()
