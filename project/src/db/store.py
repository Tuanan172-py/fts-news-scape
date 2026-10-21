"""Provide the SQLite data access and storage layer (schema v2, WAL mode)."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import sqlite3
import time

from loguru import logger

from datetime import datetime

from src.core import paths
from src.core.config import PROJECT_ROOT, resolve_db_path
from src.core.models import VN_TZ, Article, normalize_title, now_vn_iso
from src.db import registry


def _is_owner_alive(owner: str) -> bool:
    """Check whether the process that owns a lock is still alive.

    Args:
        owner: Process identity string in the form hostname:pid.

    Returns:
        True if the process exists or belongs to another host.
    """
    if not owner:
        return False
    if ":" not in owner:
        return True
    host, pid_str = owner.split(":", 1)
    if host != socket.gethostname():
        return True
    try:
        pid = int(pid_str)
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _lock_is_stale(ts_iso: str, stale_seconds: int) -> bool:
    """Check whether a lock timestamp has expired.

    Args:
        ts_iso: Lock timestamp in ISO format.
        stale_seconds: Expiry time in seconds.

    Returns:
        True if the lock is older than the allowed age.
    """
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
CREATE INDEX IF NOT EXISTS idx_agent_outputs_article_dod ON agent_outputs(article_id, dod_pass);
-- Pipeline state (morninger) — key/value bền vững qua restart (watermark/checkpoint).
CREATE TABLE IF NOT EXISTS pipeline_state (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated_at TEXT
);
-- Sổ lỗi derive Bronze→Silver (ADR 0007). Watermark KHÔNG được vượt qua hàng còn
-- dead_letter=0; đủ ngưỡng lần thử thì chuyển dead_letter=1 để thôi chặn, tránh một
-- file hỏng vĩnh viễn làm nghẽn toàn bộ Silver.
CREATE TABLE IF NOT EXISTS silver_failures (
  meta_path TEXT PRIMARY KEY,
  url_title_hash TEXT,
  fetch_ts TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  last_at TEXT,
  dead_letter INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_silver_failures_blocking
  ON silver_failures(dead_letter, fetch_ts);
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
  created_at TEXT,
  -- Nguon cua ban ghi: 'agent' (subagent LLM nop) hoac 'code_first' (tra danh muc tat dinh).
  -- Xem docs/decisions/0003-code-first-l1-delivery.md. Ban 'agent' duoc ghi de 'code_first',
  -- KHONG duoc nguoc lai.
  l1_source TEXT NOT NULL DEFAULT 'agent'
);
CREATE INDEX IF NOT EXISTS idx_l1_outputs_dod ON l1_outputs(dod_pass, created_at);
CREATE INDEX IF NOT EXISTS idx_l1_outputs_article_dod ON l1_outputs(article_id, dod_pass);
CREATE INDEX IF NOT EXISTS idx_l1_outputs_source ON l1_outputs(l1_source, dod_pass);

-- Báo cáo định kỳ (NSO/Cục Thống kê) — design 16.
-- KHÔNG dùng bảng articles: khoá nghiệp vụ là (report_type, period), KHÔNG phải
-- url_title_hash. Cùng một báo cáo được NSO mirror ở nhiều path với slug khác nhau
-- (đã gặp slug sai năm + hậu tố -2), nên dedup theo URL là sai về bản chất.
CREATE TABLE IF NOT EXISTS periodic_reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,              -- 'nso'
  report_type TEXT NOT NULL,         -- monthly | quarterly | annual
  period TEXT NOT NULL,              -- 2026-08 | 2026-Q2 | 2026
  title TEXT NOT NULL,
  source_url TEXT NOT NULL,
  remote_id TEXT,                    -- wp post id
  published_at TEXT,                 -- ISO +07:00
  modified_at TEXT,                  -- ISO +07:00 — đổi = bản hiệu đính
  html_path TEXT,                    -- Bronze HTML
  attachments_json TEXT,             -- [{url, path, sha256, bytes, content_type}]
  capture_status TEXT,
  revision INTEGER DEFAULT 1,        -- tăng khi modified_at đổi
  created_at TEXT,
  updated_at TEXT,
  UNIQUE(source, report_type, period, revision)
);
CREATE INDEX IF NOT EXISTS idx_periodic_period
  ON periodic_reports(source, report_type, period);

-- Sổ phát hiện URL (ADR 0013, rule 10): ghi TRƯỚC mọi bước lọc. Không có trạng thái "đã bỏ".
CREATE TABLE IF NOT EXISTS discovered_urls (
  url_canonical TEXT PRIMARY KEY,    -- mã bài của nguồn hoặc URL chuẩn hoá
  source_domain TEXT NOT NULL,
  first_url TEXT NOT NULL,
  first_seen_via TEXT NOT NULL,      -- listing | rss | api | sitemap | reconcile
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  n_seen INTEGER NOT NULL DEFAULT 1,
  state TEXT NOT NULL DEFAULT 'discovered',   -- discovered | captured | gone | dead_letter
  article_hash TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_disc_state ON discovered_urls(state, source_domain);
CREATE TABLE IF NOT EXISTS url_aliases (
  url TEXT PRIMARY KEY,
  url_canonical TEXT NOT NULL,
  seen_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_alias_key ON url_aliases(url_canonical);
-- Độ phủ thu thập: số bài kênh đối chiếu độc lập báo so với số bài đã có trong kho.
CREATE TABLE IF NOT EXISTS capture_coverage (
  day TEXT NOT NULL,
  source_domain TEXT NOT NULL,
  ref_n INTEGER NOT NULL,
  in_db_n INTEGER NOT NULL,
  missing_n INTEGER NOT NULL,
  backfilled_n INTEGER NOT NULL DEFAULT 0,
  checked_at TEXT,
  PRIMARY KEY (day, source_domain)
);

-- Cụm câu chuyện (ADR 0016). Bảng phái sinh: dựng lại được từ articles và Silver.
CREATE TABLE IF NOT EXISTS story_clusters (
  cluster_id TEXT PRIMARY KEY,
  canonical_id TEXT NOT NULL,
  first_seen_at TEXT,
  last_seen_at TEXT,
  n_members INTEGER,
  n_sources INTEGER,
  built_at TEXT
);
CREATE TABLE IF NOT EXISTS cluster_members (
  article_id TEXT PRIMARY KEY,
  cluster_id TEXT NOT NULL,
  role TEXT NOT NULL,                -- canonical | copy | candidate | series
  method TEXT NOT NULL,              -- sha | shingle | series | single
  score REAL,
  evidence TEXT,                     -- JSON: số liệu chung, mã CP chung, containment
  decided_by TEXT,
  decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_cm_cluster ON cluster_members(cluster_id, role);

-- Tín hiệu insight (ADR 0016). Bảng phái sinh: xoá được, dựng lại bằng signal_build.py.
CREATE TABLE IF NOT EXISTS signal_daily (
  entity_id TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  n_articles INTEGER,
  n_sources INTEGER,
  n_stories INTEGER,
  share REAL,
  ama_z REAL,
  stale_ratio REAL,
  cascade_minutes REAL,
  n_updates INTEGER,
  net_sent_story REAL,
  net_sent_volume REAL,
  net_sent_norm REAL,
  dispersion REAL,
  sent_shift REAL,
  first_source TEXT,
  coverage_pct REAL,
  built_at TEXT,
  PRIMARY KEY (entity_id, trade_date)
);
CREATE TABLE IF NOT EXISTS entity_links (
  entity_a TEXT NOT NULL,
  entity_b TEXT NOT NULL,
  window_end TEXT NOT NULL,
  n_co INTEGER,
  pmi REAL,
  PRIMARY KEY (entity_a, entity_b, window_end)
);
CREATE TABLE IF NOT EXISTS source_profile (
  source_domain TEXT NOT NULL,
  window_end TEXT NOT NULL,
  n INTEGER,
  pos_rate REAL,
  neg_rate REAL,
  lead_rate REAL,
  original_rate REAL,
  PRIMARY KEY (source_domain, window_end)
);
"""


class ArticleStore:
    """Manage all interaction with the SQLite database.

    Attributes:
        db_path: Path of the SQLite database file.
    """

    def __init__(self, db_path: str | Path | None = None, init_schema: bool = True):
        """Resolve the database path and optionally create or migrate the schema.

        Args:
            db_path: Database path; a relative path is taken from `project/`. None resolves the operational DB.
            init_schema: If True, create missing tables and apply migrations.
        """
        if db_path is None:
            self.db_path = str(resolve_db_path())
        else:
            p = Path(db_path)
            if not p.is_absolute() and not str(p).startswith("file:"):
                self.db_path = str((PROJECT_ROOT / p).resolve())
            else:
                self.db_path = str(p)
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        if init_schema:
            self.init_schema()

    def _connect(self, readonly: bool = False) -> sqlite3.Connection:
        """Open a SQLite connection with WAL and a safe timeout.

        Args:
            readonly: If True, open the connection in read-only mode.

        Returns:
            A sqlite3.Connection ready to run queries.
        """
        resolved = Path(self.db_path).resolve()
        if readonly and resolved.exists():
            uri_path = f"file:{resolved.as_posix()}?mode=ro"
            conn = sqlite3.connect(uri_path, uri=True, timeout=30.0, check_same_thread=False)
            conn.execute("PRAGMA busy_timeout=30000")
            conn.row_factory = sqlite3.Row
            return conn

        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _connect_ro(self) -> sqlite3.Connection:
        """Open a read-only connection (URI mode=ro) to avoid lock contention."""
        return self._connect(readonly=True)

    def init_schema(self) -> None:
        """Create missing tables and indexes, apply column migrations and seed the discovery ledger."""
        conn = self._connect()
        try:
            # Run _migrate BEFORE executescript: DDL with an index on a new column fails with
            # 'no such column' while the old table still lacks it. On a brand-new DB _migrate
            # does nothing (no table yet) and _SCHEMA creates every column.
            self._migrate(conn)
            conn.executescript(_SCHEMA)
            registry.backfill_from_articles(conn)
            conn.commit()
        finally:
            conn.close()

    # DDL uses CREATE TABLE IF NOT EXISTS, so it can never upgrade an existing DB.
    # Every column added later needs an idempotent ALTER step here.
    _MIGRATIONS = (
        ("l1_outputs", "l1_source", "ALTER TABLE l1_outputs ADD COLUMN l1_source TEXT NOT NULL DEFAULT 'agent'"),
    )

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Add missing columns to an existing DB; safe to run repeatedly."""
        for table, column, ddl in self._MIGRATIONS:
            try:
                have = {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
            except sqlite3.Error:
                continue                      # table absent -> _SCHEMA already creates it correctly
            if have and column not in have:
                conn.execute(ddl)
                conn.commit()

    def connect(self) -> sqlite3.Connection:
        """Open a read-write connection with all pragmas applied; used by handoff.Catalog.

        Returns:
            A sqlite3.Connection that the caller must close.
        """
        return self._connect()

    def get_by_hash(self, url_title_hash: str) -> Article | None:
        """Fetch an article by its URL-title hash.

        Args:
            url_title_hash: Hash of the article URL and title.

        Returns:
            The matching Article, or None if absent.
        """
        conn = self._connect_ro()
        try:
            row = conn.execute(
                "SELECT * FROM articles WHERE url_title_hash=?", (url_title_hash,)
            ).fetchone()
            return Article.from_row(row) if row else None
        finally:
            conn.close()

    # -- change-detection version log (phase-02) ------------------------------
    def last_version(self, url_title_hash: str) -> dict | None:
        """Fetch the latest version record of an article.

        Args:
            url_title_hash: Hash of the article URL and title.

        Returns:
            The latest `article_versions` row as a dict, or None if absent.
        """
        conn = self._connect_ro()
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
        """Insert an `article_versions` row unless the same content hash already exists.

        Args:
            row: Column values keyed by `article_versions` column name.

        Returns:
            Id of the new row, or of the existing row with the same `content_sha256`.
        """
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
            # Avoid inserting a duplicate content_sha256 when a re-derive repeats.
            existing = conn.execute(
                "SELECT id FROM article_versions WHERE url_title_hash = ? AND content_sha256 = ? "
                "ORDER BY id DESC LIMIT 1",
                (row.get("url_title_hash"), row.get("content_sha256"))
            ).fetchone()
            if existing:
                return existing["id"]

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
        """List article hashes with a version in state NEW or CONTENT_CHANGED at or after a watermark.

        Args:
            watermark_iso: ISO timestamp lower bound for `captured_at`.

        Returns:
            Distinct `url_title_hash` values.
        """
        conn = self._connect_ro()
        try:
            rows = conn.execute(
                "SELECT DISTINCT url_title_hash FROM article_versions "
                "WHERE state IN ('NEW','CONTENT_CHANGED') AND captured_at >= ?",
                (watermark_iso,),
            ).fetchall()
            return [r["url_title_hash"] for r in rows]
        finally:
            conn.close()

    # -- agent output store ----------------------------------------------------
    def get_agent_output(self, article_id: str, raw_sha256: str) -> dict | None:
        """Fetch the stored output for (article_id, raw_sha256) for an idempotent replay.

        Args:
            article_id: Article identifier.
            raw_sha256: SHA-256 of the raw capture.

        Returns:
            The `agent_outputs` row as a dict, or None if absent.
        """
        conn = self._connect_ro()
        try:
            row = conn.execute(
                "SELECT * FROM agent_outputs WHERE article_id=? AND raw_sha256=?",
                (article_id, raw_sha256),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def set_agent_dod(self, row_id: int, dod_pass: int, dod_reasons: str) -> None:
        """Update the Definition-of-Done check status of an agent output record.

        Args:
            row_id: Primary key of the row in `agent_outputs`.
            dod_pass: DoD status flag (1 passed, 0 failed).
            dod_reasons: Reasons or detailed check result.
        """
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE agent_outputs SET dod_pass = ?, dod_reasons = ? WHERE id = ?",
                (int(dod_pass), dod_reasons, int(row_id)),
            )
            conn.commit()
        finally:
            conn.close()

    def insert_agent_output(self, row: dict) -> int:
        """Upsert one output by UNIQUE(article_id, raw_sha256).

        Args:
            row: Column values keyed by `agent_outputs` column name.

        Returns:
            Row id, or -1 if the row cannot be read back.
        """
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

    # -- L1 entity-recognition store (handoff layer 1) -------------------------
    def upsert_l1_task(self, row: dict) -> None:
        """Upsert the code-first result of one article, keeping the existing status.

        Args:
            row: Column values keyed by `l1_tasks` column name.
        """
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
        """Fetch the L1 task of an article.

        Args:
            article_id: Article identifier.

        Returns:
            The `l1_tasks` row as a dict, or None if absent.
        """
        conn = self._connect_ro()
        try:
            r = conn.execute("SELECT * FROM l1_tasks WHERE article_id=?", (article_id,)).fetchone()
            return dict(r) if r else None
        finally:
            conn.close()

    def set_l1_status(self, article_id: str, status: str, *, done_at: str | None = None,
                      error: str | None = None) -> None:
        """Set the status of an L1 task.

        Args:
            article_id: Article identifier.
            status: New status: pending, done or failed.
            done_at: Completion timestamp.
            error: Error message, if any.
        """
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE l1_tasks SET status=?, done_at=?, error=? WHERE article_id=?",
                (status, done_at, error, article_id))
            conn.commit()
        finally:
            conn.close()

    def insert_l1_output(self, row: dict) -> None:
        """Upsert the L1 agent review output by UNIQUE(article_id).

        Args:
            row: Column values keyed by `l1_outputs` column name; `l1_source` defaults to `agent`.
        """
        cols = ("article_id", "output_json", "recognized", "agent_provider",
                "model_used", "confidence", "dod_pass", "dod_reasons", "created_at",
                "l1_source")
        row = {**row, "l1_source": row.get("l1_source") or "agent"}
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
        """Fetch the L1 output of an article.

        Args:
            article_id: Article identifier.

        Returns:
            The `l1_outputs` row as a dict, or None if absent.
        """
        conn = self._connect_ro()
        try:
            r = conn.execute("SELECT * FROM l1_outputs WHERE article_id=?", (article_id,)).fetchone()
            return dict(r) if r else None
        finally:
            conn.close()

    def insert(self, article: Article, conn: sqlite3.Connection | None = None) -> bool:
        """Insert one article.

        Args:
            article: Article to insert.
            conn: Existing connection to use; None opens and commits its own.

        Returns:
            True if a new row was inserted, False if it already exists (duplicate URL or hash) or the insert failed.
        """
        own = conn is None
        if own:
            conn = self._connect()
        try:
            cur = conn.execute(_INSERT_SQL, article.to_row())
            registry.mark_captured(conn, article.url, article.source_domain,
                                   article.url_title_hash)
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
        """Insert a batch in one transaction (BEGIN IMMEDIATE).

        Args:
            articles: Articles to insert.
            conn: Existing connection to use; None opens its own.

        Returns:
            Number of new rows.
        """
        if not articles:
            return 0
        own = conn is None
        if own:
            conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            before = conn.total_changes
            conn.executemany(_INSERT_SQL, [a.to_row() for a in articles])
            inserted = conn.total_changes - before      # count BEFORE writing seen_articles,
                                                        # or that table's rows would be counted too
            # Mark `seen` in the SAME transaction as `articles`. Marking at scrape time while the
            # `articles` row is written asynchronously by DBWriter would let any interruption in
            # between (process exit, writer death, unflushed queue) leave an article marked seen
            # forever without an `articles` row, so every later cycle skips it while
            # Bronze/Silver/work_items/L1/Gold keep running from the scraped raw copy.
            conn.executemany(
                "INSERT OR IGNORE INTO seen_articles (hash, title_norm, source_domain, seen_at) "
                "VALUES (?, ?, ?, ?)",
                [(a.url_title_hash, normalize_title(a.title), a.source_domain, time.time())
                 for a in articles])
            for a in articles:
                registry.mark_captured(conn, a.url, a.source_domain, a.url_title_hash)
            conn.commit()
            return inserted
        except sqlite3.Error as e:
            conn.rollback()
            logger.error("DB batch insert failed ({} articles): {}", len(articles), e)
            return 0
        except BaseException:
            # KeyboardInterrupt, MemoryError and similar: do not leave a transaction open on
            # the long-lived DBWriter connection.
            conn.rollback()
            raise
        finally:
            if own:
                conn.close()

    def get_recent(
        self, limit: int = 20, source_domain: str | None = None
    ) -> list[Article]:
        """Fetch the most recently fetched articles.

        Args:
            limit: Maximum number of articles.
            source_domain: Restrict to one source domain; None means all.

        Returns:
            Articles ordered by `fetched_at`, newest first.
        """
        conn = self._connect_ro()
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
        """Count articles per domain fetched at or after a timestamp, for metrics and monitoring.

        Args:
            since_iso: ISO timestamp lower bound for `fetched_at`.

        Returns:
            Mapping of source domain to article count.
        """
        conn = self._connect_ro()
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
        """Count all stored articles.

        Returns:
            Number of rows in `articles`.
        """
        conn = self._connect_ro()
        try:
            return conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        finally:
            conn.close()

    # -- pipeline state (morninger watermark/checkpoint) ----------------------
    def get_state(self, key: str) -> str | None:
        """Read a key from `pipeline_state`.

        Args:
            key: State key.

        Returns:
            The stored value, or None if absent.
        """
        conn = self._connect_ro()
        try:
            row = conn.execute(
                "SELECT value FROM pipeline_state WHERE key=?", (key,)
            ).fetchone()
            return row["value"] if row else None
        finally:
            conn.close()

    def set_state(self, key: str, value: str) -> None:
        """Upsert one key in `pipeline_state`.

        Args:
            key: State key.
            value: Value to store.
        """
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

    # -- Bronze-to-Silver derive failure ledger (ADR 0007) ---------------------
    @staticmethod
    def canonical_meta_key(meta_path: str) -> str:
        """Normalize a `silver_failures` key to a path relative to the data root.

        One Bronze file can be named by an absolute or relative path, with forward or
        backward slashes, with or without the legacy `data/` prefix. A non-canonical key
        means an old failure row is never cleared or retried and pins the watermark forever.

        Args:
            meta_path: Path of the `.meta.json` file.

        Returns:
            Path with forward slashes, relative when the file is inside the data root.
        """
        if Path(meta_path).is_absolute():
            return paths.to_data_relative(meta_path).replace("\\", "/")
        return paths.strip_legacy_prefix(str(meta_path))

    def normalize_silver_failure_keys(self) -> int:
        """Rewrite every key in `silver_failures` to canonical form and merge duplicate rows.

        Duplicate rows keep the largest attempt count and the largest dead-letter flag.

        Returns:
            Number of rows rekeyed or merged.
        """
        conn = self._connect()
        changed = 0
        try:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("SELECT meta_path FROM silver_failures").fetchall()
            for (key,) in [(r[0],) for r in rows]:
                canon = self.canonical_meta_key(key)
                if canon == key:
                    continue
                old = conn.execute("SELECT * FROM silver_failures WHERE meta_path=?",
                                   (key,)).fetchone()
                dup = conn.execute("SELECT attempts, dead_letter FROM silver_failures "
                                   "WHERE meta_path=?", (canon,)).fetchone()
                if dup:
                    conn.execute(
                        "UPDATE silver_failures SET attempts=?, dead_letter=? WHERE meta_path=?",
                        (max(old["attempts"], dup[0]), max(old["dead_letter"], dup[1]), canon))
                    conn.execute("DELETE FROM silver_failures WHERE meta_path=?", (key,))
                else:
                    conn.execute("UPDATE silver_failures SET meta_path=? WHERE meta_path=?",
                                 (canon, key))
                changed += 1
            conn.commit()
            return changed
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def record_silver_failure(self, meta_path: str, fetch_ts: str, error: str,
                              max_attempts: int,
                              url_title_hash: str = "") -> int:
        """Record one FAILED derive of a Bronze file and increment its attempt count.

        Args:
            meta_path: Path of the `.meta.json` file (primary key).
            fetch_ts: Timestamp used to block the watermark.
            error: Latest error message.
            max_attempts: Once reached, the row becomes dead-letter and stops blocking the watermark.
            url_title_hash: Article hash if known.

        Returns:
            Attempt count after the increment.
        """
        meta_path = self.canonical_meta_key(meta_path)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT attempts FROM silver_failures WHERE meta_path=?",
                (meta_path,)).fetchone()
            attempts = (row["attempts"] if row else 0) + 1
            conn.execute(
                "INSERT OR REPLACE INTO silver_failures "
                "(meta_path, url_title_hash, fetch_ts, attempts, last_error, "
                " last_at, dead_letter) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (meta_path, url_title_hash, fetch_ts, attempts, error[:500],
                 now_vn_iso(), 1 if attempts >= max_attempts else 0))
            conn.commit()
            return attempts
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def clear_silver_failure(self, meta_path: str) -> None:
        """Remove a file from the failure ledger after a successful derive.

        Args:
            meta_path: Path of the `.meta.json` file.
        """
        conn = self._connect()
        try:
            conn.execute("DELETE FROM silver_failures WHERE meta_path IN (?, ?)",
                         (meta_path, self.canonical_meta_key(meta_path)))
            conn.commit()
        finally:
            conn.close()

    def blocking_silver_failure_ts(self) -> str:
        """Return the smallest `fetch_ts` among failures that are NOT yet dead-letter.

        Returns:
            Timestamp that blocks the watermark, or an empty string if nothing blocks.
        """
        conn = self._connect_ro()
        try:
            row = conn.execute(
                "SELECT min(fetch_ts) AS ts FROM silver_failures "
                "WHERE dead_letter=0 AND fetch_ts <> ''").fetchone()
            return (row["ts"] or "") if row else ""
        finally:
            conn.close()

    def count_silver_failures(self) -> tuple[int, int]:
        """Count the outstanding derive failures.

        Returns:
            Pair (number blocking the watermark, number dead-lettered).
        """
        conn = self._connect_ro()
        try:
            row = conn.execute(
                "SELECT sum(CASE WHEN dead_letter=0 THEN 1 ELSE 0 END) AS blocking, "
                "       sum(CASE WHEN dead_letter=1 THEN 1 ELSE 0 END) AS dead "
                "FROM silver_failures").fetchone()
            return (int(row["blocking"] or 0), int(row["dead"] or 0))
        finally:
            conn.close()

    # -- advisory scheduler lock (prevents two schedulers running at once) -------
    def try_acquire_lock(self, name: str, owner: str, stale_seconds: int) -> bool:
        """Take a lock through `pipeline_state` (atomic BEGIN IMMEDIATE).

        Args:
            name: Lock name.
            owner: Identity of the requesting process.
            stale_seconds: Age in seconds after which another owner's lock counts as stale.

        Returns:
            True if the lock is free, already held by this owner, stale, or its previous
            owner died. False if another owner holds a fresh lock.
        """
        key = f"lock:{name}"
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT value, updated_at FROM pipeline_state WHERE key=?", (key,)
            ).fetchone()
            if row is not None and (row["value"] or "") != owner:
                owner_alive = _is_owner_alive(row["value"] or "")
                if owner_alive and not _lock_is_stale(row["updated_at"] or "", stale_seconds):
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

    def release_lock(self, name: str, owner: str) -> bool:
        """Release a lock if this owner holds it (atomic).

        Args:
            name: Lock name.
            owner: Identity of the releasing process.

        Returns:
            True if the lock was held by this owner and released, otherwise False.
        """
        key = f"lock:{name}"
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT value FROM pipeline_state WHERE key=?", (key,)
            ).fetchone()
            if row is not None and (row["value"] or "") == owner:
                conn.execute("DELETE FROM pipeline_state WHERE key=?", (key,))
                conn.commit()
                return True
            conn.commit()
            return False
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def refresh_lock(self, name: str, owner: str) -> None:
        """Keep a lock fresh with a heartbeat, called once per cycle by the lock owner.

        Args:
            name: Lock name.
            owner: Identity of the lock owner.
        """
        self.set_state(f"lock:{name}", owner)
