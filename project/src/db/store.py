"""
Store layer — SQLite duy nhất (spec §7), schema v2, WAL mode.

Mọi connection đều bật: journal_mode=WAL, busy_timeout=5000, synchronous=NORMAL.
Ghi hàng loạt đi qua DBWriter (src/db/writer.py) — single-writer pattern.
"""

from __future__ import annotations

import os
import sqlite3

from loguru import logger

from datetime import datetime

from src.core.models import VN_TZ, Article, now_vn_iso


def _lock_is_stale(ts_iso: str, stale_seconds: int) -> bool:
    """True nếu timestamp lock quá cũ (chủ cũ có thể đã chết) → cho phép chiếm lại."""
    try:
        age = (datetime.now(VN_TZ) - datetime.fromisoformat(ts_iso)).total_seconds()
    except (ValueError, TypeError):
        return True
    return age > stale_seconds

_COLUMNS = (
    "url",
    "url_title_hash",
    "title",
    "summary",
    "content_html",
    "content_text",
    "published_at",
    "author",
    "source_domain",
    "symbols",
    "categories",
    "sentiment",
    "sentiment_score",
    "fetched_at",
    "processed_at",
    "metadata_json",
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
-- Change-detection version log (phase-02) — append-only, mỗi hàng = 1 bản capture.
CREATE TABLE IF NOT EXISTS article_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url_title_hash TEXT NOT NULL,
  source_domain TEXT,
  captured_at TEXT,
  content_sha256 TEXT,
  simhash64 TEXT,
  dom_path_sig TEXT,
  capture_status TEXT,
  prev_version_id INTEGER,
  hamming_content INTEGER,
  dom_changed INTEGER,
  selector_drift INTEGER,
  state TEXT,
  recommendation TEXT
);
CREATE INDEX IF NOT EXISTS idx_versions_hash ON article_versions(url_title_hash, captured_at);
CREATE INDEX IF NOT EXISTS idx_versions_state ON article_versions(state, captured_at);
-- Handoff catalog (phase-03) — hàng đợi việc cho agent, exactly-once.
CREATE TABLE IF NOT EXISTS work_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  article_id TEXT NOT NULL,
  raw_sha256 TEXT NOT NULL,
  domain TEXT,
  package_path TEXT,
  status TEXT NOT NULL DEFAULT 'pending',   -- pending|claimed|done|failed|held
  claimed_by TEXT,
  claimed_at TEXT,
  done_at TEXT,
  error TEXT,
  change_state TEXT,
  enqueued_at TEXT,
  UNIQUE(article_id, raw_sha256)
);
CREATE INDEX IF NOT EXISTS idx_work_items_status ON work_items(status, enqueued_at);
-- Agent output store (Vòng 3 infra) — 1 output chuẩn / bản raw (idempotency key).
-- KHÔNG có LLM ở producer; hàng ghi vào đây do agent NGOÀI (do người dùng điều khiển)
-- nộp qua ingest → validate(agent-output-v1) + DoD trước khi lưu. dod_pass=1 ⇒ đạt.
CREATE TABLE IF NOT EXISTS agent_outputs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  article_id TEXT NOT NULL,
  raw_sha256 TEXT NOT NULL,
  work_item_id INTEGER,
  output_json TEXT NOT NULL,     -- toàn bộ agent-output-v1 (nguyên bản agent nộp)
  agent_provider TEXT,           -- rút từ processing_metadata (audit)
  model_used TEXT,
  confidence REAL,
  dod_pass INTEGER DEFAULT 0,    -- 1 = qua Definition-of-Done; 0 = chưa đạt
  dod_reasons TEXT,              -- JSON list lý do fail (rỗng nếu pass)
  created_at TEXT,
  UNIQUE(article_id, raw_sha256)
);
CREATE INDEX IF NOT EXISTS idx_agent_outputs_dod ON agent_outputs(dod_pass, created_at);
-- Pipeline state (morninger) — key/value bền vững qua restart (watermark/checkpoint).
CREATE TABLE IF NOT EXISTS pipeline_state (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated_at TEXT
);
-- L1 entity-recognition (lớp 1 handoff) — code-first + trạng thái audit của agent.
-- 1 hàng / article. status = trạng thái tra soát của agent (pending → done/failed).
CREATE TABLE IF NOT EXISTS l1_tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  article_id TEXT NOT NULL UNIQUE,
  domain TEXT,
  title TEXT,
  code_first_json TEXT,          -- kết quả code-first (entities/industries/relevance)
  route TEXT,                    -- resolved | needs_agent
  packet_path TEXT,
  status TEXT NOT NULL DEFAULT 'pending',   -- pending|done|failed
  enqueued_at TEXT,
  done_at TEXT,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_l1_tasks_status ON l1_tasks(status, enqueued_at);
-- Output tra soát của agent L1 (l1-entity-output-v1) sau khi qua DoD.
CREATE TABLE IF NOT EXISTS l1_outputs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  article_id TEXT NOT NULL UNIQUE,
  output_json TEXT NOT NULL,
  recognized INTEGER,
  agent_provider TEXT,
  model_used TEXT,
  confidence REAL,
  dod_pass INTEGER DEFAULT 0,
  dod_reasons TEXT,
  created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_l1_outputs_dod ON l1_outputs(dod_pass, created_at);
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

    def connect(self) -> sqlite3.Connection:
        """Public connection (đủ pragmas). Caller tự đóng. Dùng bởi handoff.Catalog."""
        return self._connect()

    def get_by_hash(self, url_title_hash: str) -> Article | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM articles WHERE url_title_hash=?", (url_title_hash,)
            ).fetchone()
            return Article.from_row(row) if row else None
        finally:
            conn.close()

    # -- change-detection version log (phase-02) ------------------------------
    def last_version(self, url_title_hash: str) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM article_versions WHERE url_title_hash=? "
                "ORDER BY id DESC LIMIT 1",
                (url_title_hash,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def insert_version(self, row: dict) -> int:
        cols = (
            "url_title_hash",
            "source_domain",
            "captured_at",
            "content_sha256",
            "simhash64",
            "dom_path_sig",
            "capture_status",
            "prev_version_id",
            "hamming_content",
            "dom_changed",
            "selector_drift",
            "state",
            "recommendation",
        )
        conn = self._connect()
        try:
            cur = conn.execute(
                f"INSERT INTO article_versions ({', '.join(cols)}) "
                f"VALUES ({', '.join('?' for _ in cols)})",
                tuple(row.get(c) for c in cols),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def changed_since(self, watermark_iso: str = "") -> list[str]:
        """url_title_hash có bản version state ∈ {NEW,CONTENT_CHANGED} sau watermark."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT DISTINCT url_title_hash FROM article_versions "
                "WHERE state IN ('NEW','CONTENT_CHANGED') AND captured_at >= ?",
                (watermark_iso,),
            ).fetchall()
            return [r["url_title_hash"] for r in rows]
        finally:
            conn.close()

    # -- agent output store (Vòng 3 infra) ------------------------------------
    def get_agent_output(self, article_id: str, raw_sha256: str) -> dict | None:
        """Output đã lưu cho (article_id, raw_sha256) — idempotent replay."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM agent_outputs WHERE article_id=? AND raw_sha256=?",
                (article_id, raw_sha256),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def insert_agent_output(self, row: dict) -> int:
        """Upsert 1 output theo UNIQUE(article_id, raw_sha256). Trả row id."""
        cols = (
            "article_id",
            "raw_sha256",
            "work_item_id",
            "output_json",
            "agent_provider",
            "model_used",
            "confidence",
            "dod_pass",
            "dod_reasons",
            "created_at",
        )
        conn = self._connect()
        try:
            conn.execute(
                f"INSERT OR REPLACE INTO agent_outputs ({', '.join(cols)}) "
                f"VALUES ({', '.join('?' for _ in cols)})",
                tuple(row.get(c) for c in cols),
            )
            conn.commit()
            r = conn.execute(
                "SELECT id FROM agent_outputs WHERE article_id=? AND raw_sha256=?",
                (row.get("article_id"), row.get("raw_sha256")),
            ).fetchone()
            return r["id"] if r else -1
        finally:
            conn.close()

    # -- L1 entity-recognition store (lớp 1 handoff) --------------------------
    def upsert_l1_task(self, row: dict) -> None:
        """Ghi/nhật kết quả code-first cho 1 article; GIỮ nguyên status nếu đã có."""
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO l1_tasks (article_id, domain, title, code_first_json, "
                "route, packet_path, status, enqueued_at) "
                "VALUES (:article_id,:domain,:title,:code_first_json,:route,:packet_path,"
                "'pending',:enqueued_at) "
                "ON CONFLICT(article_id) DO UPDATE SET "
                "domain=excluded.domain, title=excluded.title, "
                "code_first_json=excluded.code_first_json, route=excluded.route, "
                "packet_path=excluded.packet_path",
                {k: row.get(k) for k in
                 ("article_id", "domain", "title", "code_first_json", "route",
                  "packet_path", "enqueued_at")},
            )
            conn.commit()
        finally:
            conn.close()

    def get_l1_task(self, article_id: str) -> dict | None:
        conn = self._connect()
        try:
            r = conn.execute("SELECT * FROM l1_tasks WHERE article_id=?", (article_id,)).fetchone()
            return dict(r) if r else None
        finally:
            conn.close()

    def set_l1_status(self, article_id: str, status: str, *, done_at: str | None = None,
                      error: str | None = None) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE l1_tasks SET status=?, done_at=?, error=? WHERE article_id=?",
                (status, done_at, error, article_id))
            conn.commit()
        finally:
            conn.close()

    def insert_l1_output(self, row: dict) -> None:
        """Upsert output tra soát agent L1 theo UNIQUE(article_id)."""
        cols = ("article_id", "output_json", "recognized", "agent_provider",
                "model_used", "confidence", "dod_pass", "dod_reasons", "created_at")
        conn = self._connect()
        try:
            conn.execute(
                f"INSERT OR REPLACE INTO l1_outputs ({', '.join(cols)}) "
                f"VALUES ({', '.join('?' for _ in cols)})",
                tuple(row.get(c) for c in cols))
            conn.commit()
        finally:
            conn.close()

    def get_l1_output(self, article_id: str) -> dict | None:
        conn = self._connect()
        try:
            r = conn.execute("SELECT * FROM l1_outputs WHERE article_id=?", (article_id,)).fetchone()
            return dict(r) if r else None
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

    def insert_batch(
        self, articles: list[Article], conn: sqlite3.Connection | None = None
    ) -> int:
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

    def get_recent(
        self, limit: int = 20, source_domain: str | None = None
    ) -> list[Article]:
        conn = self._connect()
        try:
            if source_domain:
                rows = conn.execute(
                    "SELECT * FROM articles WHERE source_domain=? "
                    "ORDER BY fetched_at DESC LIMIT ?",
                    (source_domain, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM articles ORDER BY fetched_at DESC LIMIT ?", (limit,)
                ).fetchall()
            return [Article.from_row(r) for r in rows]
        finally:
            conn.close()

    def count_by_domain(self, since_iso: str = "") -> dict[str, int]:
        """Số article mỗi domain (fetched_at >= since_iso) — cho metrics/monitoring."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT source_domain, COUNT(*) AS n FROM articles "
                "WHERE fetched_at >= ? GROUP BY source_domain",
                (since_iso,),
            ).fetchall()
            return {r["source_domain"]: r["n"] for r in rows}
        finally:
            conn.close()

    def count(self) -> int:
        conn = self._connect()
        try:
            return conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        finally:
            conn.close()

    # -- pipeline state (morninger watermark/checkpoint) ----------------------
    def get_state(self, key: str) -> str | None:
        """Đọc giá trị key từ pipeline_state. None nếu chưa có."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT value FROM pipeline_state WHERE key=?", (key,)
            ).fetchone()
            return row["value"] if row else None
        finally:
            conn.close()

    def set_state(self, key: str, value: str) -> None:
        """Ghi/ghi đè 1 key trong pipeline_state (upsert)."""
        conn = self._connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO pipeline_state (key, value, updated_at) "
                "VALUES (?, ?, ?)",
                (key, value, now_vn_iso()),
            )
            conn.commit()
        finally:
            conn.close()

    # -- advisory scheduler lock (Fix F: chống chạy 2 scheduler cùng lúc) -------
    def try_acquire_lock(self, name: str, owner: str, stale_seconds: int) -> bool:
        """Chiếm lock qua pipeline_state (atomic BEGIN IMMEDIATE). True nếu lock trống /
        của chính owner / đã cũ (stale). False nếu owner khác đang giữ lock còn tươi."""
        key = f"lock:{name}"
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT value, updated_at FROM pipeline_state WHERE key=?", (key,)
            ).fetchone()
            if row is not None and (row["value"] or "") != owner \
                    and not _lock_is_stale(row["updated_at"] or "", stale_seconds):
                conn.rollback()
                return False
            conn.execute(
                "INSERT OR REPLACE INTO pipeline_state (key, value, updated_at) "
                "VALUES (?, ?, ?)", (key, owner, now_vn_iso()))
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def refresh_lock(self, name: str, owner: str) -> None:
        """Nhịp tim giữ lock còn tươi (gọi mỗi cycle của chủ sở hữu lock)."""
        self.set_state(f"lock:{name}", owner)
