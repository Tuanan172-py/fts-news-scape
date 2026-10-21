"""Check seen articles by exact hash and record URL discovery in the ledger."""

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
    """Duplicate-check cache backed by the `seen_articles` table in SQLite.

    Attributes:
        store: ArticleStore that manages the database.
    """

    def __init__(self, store: ArticleStore, legacy_json_path: str = _LEGACY_JSON):
        """Open the cache on the store connection and migrate any legacy JSON cache.

        Args:
            store: ArticleStore that manages the database.
            legacy_json_path: Path of the legacy `dedup_cache.json` to import and remove.
        """
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
        """Check whether an article was seen before, by the SHA-256(url + title) hash.

        Args:
            url: Article URL.
            title: Article title.

        Returns:
            True if the article is already in the cache.
        """
        h = sha256_hash(url, title)
        row = self._conn.execute(
            "SELECT 1 FROM seen_articles WHERE hash=?", (h,)).fetchone()
        return row is not None

    def mark_seen(self, url: str, title: str, source_domain: str = "") -> None:
        """Mark an article as seen in the duplicate cache.

        Args:
            url: Article URL.
            title: Article title.
            source_domain: Domain of the news source.
        """
        self._conn.execute(
            "INSERT OR IGNORE INTO seen_articles (hash, title_norm, source_domain, seen_at) "
            "VALUES (?, ?, ?, ?)",
            (sha256_hash(url, title), normalize_title(title), source_domain, time.time()),
        )
        self._conn.commit()

    def discover(self, url: str, source_domain: str, via: str = "listing") -> tuple[str, bool, bool]:
        """Record a URL in the discovery ledger before any filter.

        Args:
            url: URL as returned by the source.
            source_domain: Source domain.
            via: Discovery channel: listing, rss, api, sitemap or reconcile.

        Returns:
            Tuple of (article key, is new article, is a URL form different from the first one seen).
        """
        res = registry.discover(self._conn, url, source_domain, via)
        self._conn.commit()
        return res

    def is_captured(self, key: str) -> bool:
        """Check whether the article with this key was already stored as an article.

        Args:
            key: Article key from `src.core.urlnorm.url_key`.

        Returns:
            True if the discovery ledger records the captured state.
        """
        return registry.is_captured(self._conn, key)

    def known_keys(self, keys: list[str]) -> set[str]:
        """Filter the article keys already stored as articles.

        Args:
            keys: Article keys to look up.

        Returns:
            Keys already in the captured state, used as the pagination stop marker.
        """
        return registry.known_keys(self._conn, keys)

    def cleanup(self, max_age_days: int = 30) -> int:
        """Delete seen records older than the given number of days.

        Args:
            max_age_days: Maximum retention in days.

        Returns:
            Number of records deleted.
        """
        cutoff = time.time() - max_age_days * 86400
        cur = self._conn.execute("DELETE FROM seen_articles WHERE seen_at < ?", (cutoff,))
        self._conn.commit()
        return cur.rowcount

    def count(self) -> int:
        """Count the records in the `seen_articles` table.

        Returns:
            Number of records in the table.
        """
        return self._conn.execute("SELECT COUNT(*) FROM seen_articles").fetchone()[0]

    def close(self) -> None:
        """Close the database connection of the cache."""
        self._conn.close()
