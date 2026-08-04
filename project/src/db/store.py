"""
Store layer — SQLite duy nhất (spec §7), schema v2, WAL mode.

Mọi connection đều bật: journal_mode=WAL, busy_timeout=5000, synchronous=NORMAL.
Ghi hàng loạt đi qua DBWriter (src/db/writer.py) — single-writer pattern.
"""

from __future__ import annotations

import os
import sqlite3

from loguru import logger

from src.core.models import Article

_COLUMNS = (
    "url", "url_title_hash", "title", "summary", "content_html", "content_text",
    "published_at", "author", "source_domain", "symbols", "categories",
    "sentiment", "sentiment_score", "fetched_at", "processed_at", "metadata_json",
)

_INSERT_SQL = (
    f"INSERT OR IGNORE INTO articles ({', '.join(_COLUMNS)}) "
    f"VALUES ({', '.join(':' + c for c in _COLUMNS)})"
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL UNIQUE,
  url_title_hash TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  summary TEXT,
  content_html TEXT,
  content_text TEXT,
  published_at TEXT,
  author TEXT,
  source_domain TEXT NOT NULL,
  symbols TEXT,
  categories TEXT,
  sentiment TEXT,
  sentiment_score REAL,
  fetched_at TEXT NOT NULL,
  processed_at TEXT,
  metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_domain, fetched_at);
CREATE TABLE IF NOT EXISTS seen_articles (
  hash TEXT PRIMARY KEY,
  title_norm TEXT,
  source_domain TEXT,
  seen_at REAL
);
CREATE INDEX IF NOT EXISTS idx_seen_source ON seen_articles(source_domain, seen_at);
CREATE TABLE IF NOT EXISTS scraper_heartbeat (
  scraper_name TEXT PRIMARY KEY,
  last_run_ts TEXT,
  status TEXT,                  -- running | ok | failed
  error_msg TEXT,
  consecutive_failures INTEGER DEFAULT 0,
  cycle_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS scraper_metrics (
  ts TEXT,
  scraper_name TEXT,
  articles_fetched INTEGER,
  articles_new INTEGER,
  errors INTEGER,
  duration_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_metrics_scraper ON scraper_metrics(scraper_name, ts);
"""


class ArticleStore:
    """SQLite article store, schema v2. Thread nào cần thì tự mở connection riêng."""

    def __init__(self, db_path: str = "data/monocle.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.init_schema()

    def _connect(self) -> sqlite3.Connection:
        """Connection mới với đủ pragmas. Caller tự đóng (hoặc dùng suốt đời thread).

        check_same_thread=False: APScheduler chạy job trong worker thread khác
        thread tạo DedupCache; truy cập vẫn tuần tự (max_instances=1) nên an toàn.
        """
        conn = sqlite3.connect(self.db_path, timeout=5.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def insert(self, article: Article, conn: sqlite3.Connection | None = None) -> bool:
        """Insert 1 article. True nếu row mới, False nếu đã tồn tại (URL/hash trùng)."""
        own = conn is None
        if own:
            conn = self._connect()
        try:
            cur = conn.execute(_INSERT_SQL, article.to_row())
            if own:
                conn.commit()
            return cur.rowcount > 0
        except sqlite3.Error as e:
            logger.error("DB insert failed for {}: {}", article.url, e)
            return False
        finally:
            if own:
                conn.close()

    def insert_batch(self, articles: list[Article],
                     conn: sqlite3.Connection | None = None) -> int:
        """Insert batch trong 1 transaction (BEGIN IMMEDIATE). Trả về số row mới."""
        if not articles:
            return 0
        own = conn is None
        if own:
            conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            before = conn.total_changes
            conn.executemany(_INSERT_SQL, [a.to_row() for a in articles])
            conn.commit()
            return conn.total_changes - before
        except sqlite3.Error as e:
            conn.rollback()
            logger.error("DB batch insert failed ({} articles): {}", len(articles), e)
            return 0
        except BaseException:
            # KeyboardInterrupt/MemoryError...: không để transaction treo trên
            # connection dài hạn của DBWriter
            conn.rollback()
            raise
        finally:
            if own:
                conn.close()

    def get_recent(self, limit: int = 20, source_domain: str | None = None) -> list[Article]:
        conn = self._connect()
        try:
            if source_domain:
                rows = conn.execute(
                    "SELECT * FROM articles WHERE source_domain=? "
                    "ORDER BY fetched_at DESC LIMIT ?", (source_domain, limit)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM articles ORDER BY fetched_at DESC LIMIT ?",
                    (limit,)).fetchall()
            return [Article.from_row(r) for r in rows]
        finally:
            conn.close()

    def count_by_domain(self, since_iso: str = "") -> dict[str, int]:
        """Số article mỗi domain (fetched_at >= since_iso) — cho metrics/monitoring."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT source_domain, COUNT(*) AS n FROM articles "
                "WHERE fetched_at >= ? GROUP BY source_domain", (since_iso,)).fetchall()
            return {r["source_domain"]: r["n"] for r in rows}
        finally:
            conn.close()

    def count(self) -> int:
        conn = self._connect()
        try:
            return conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        finally:
            conn.close()
