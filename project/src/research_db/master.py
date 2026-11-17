"""Keep the local gated state of the production news lakehouse and track which day partitions changed."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable

from src.core import paths
from src.core.models import now_vn_iso
from src.research_db import gate

DEFAULT_MAX_RETRACT_RATIO = 0.05

_DDL = """
CREATE TABLE IF NOT EXISTS articles (
  article_id TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  source_domain TEXT,
  published_at TEXT,
  fetched_at TEXT,
  published_date TEXT,
  summary TEXT NOT NULL,
  key_points_json TEXT NOT NULL,
  implication TEXT NOT NULL,
  sentiment TEXT NOT NULL,
  time_sensitivity TEXT NOT NULL,
  citations_json TEXT NOT NULL,
  symbols TEXT,
  categories TEXT,
  raw_sha256 TEXT,
  analysis_provider TEXT,
  analysis_model TEXT,
  analysis_at TEXT,
  entity_at TEXT,
  entity_source TEXT,
  inherited_from TEXT,
  src_agent_output_id INTEGER NOT NULL,
  src_l1_output_id INTEGER NOT NULL,
  gate_version TEXT NOT NULL,
  synced_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(published_date);
CREATE TABLE IF NOT EXISTS article_entities (
  article_id TEXT NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL,
  surface TEXT,
  entity_id TEXT,
  type TEXT NOT NULL,
  method TEXT,
  in_list INTEGER NOT NULL,
  confidence REAL,
  scope TEXT NOT NULL DEFAULT 'title',
  role TEXT NOT NULL DEFAULT 'primary',
  provenance TEXT NOT NULL DEFAULT 'BOTH',
  confidence_tier TEXT NOT NULL DEFAULT 'HIGH',
  first_para_idx INTEGER,
  PRIMARY KEY (article_id, ordinal)
);
CREATE TABLE IF NOT EXISTS entity_candidates_log (
  surface_norm TEXT PRIMARY KEY,
  surface_sample TEXT NOT NULL,
  article_count INTEGER NOT NULL DEFAULT 0,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  sample_article_id TEXT
);
CREATE TABLE IF NOT EXISTS _rejects (
  article_id TEXT PRIMARY KEY,
  src_agent_output_id INTEGER NOT NULL,
  src_l1_output_id INTEGER NOT NULL,
  reasons_json TEXT NOT NULL,
  rejected_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS _dirty_days (
  day TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS _partitions (
  path TEXT PRIMARY KEY,
  day TEXT NOT NULL,
  rows INTEGER NOT NULL,
  size INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  written_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS _meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

_ARTICLE_COLUMNS = (
    "article_id", "url", "title", "source_domain", "published_at", "fetched_at",
    "published_date", "summary", "key_points_json", "implication", "sentiment",
    "time_sensitivity", "citations_json", "symbols", "categories", "raw_sha256",
    "analysis_provider", "analysis_model", "analysis_at", "entity_at", "entity_source",
    "inherited_from", "src_agent_output_id", "src_l1_output_id", "gate_version", "synced_at",
)
_UPSERT_SQL = (
    f"INSERT OR REPLACE INTO articles ({', '.join(_ARTICLE_COLUMNS)}) "
    f"VALUES ({', '.join(':' + c for c in _ARTICLE_COLUMNS)})"
)


class RetractionGuardError(RuntimeError):
    """Raised when a sync would remove more published articles than the safety ratio allows."""


@dataclass
class SyncResult:
    """Outcome of one gate pass into the master database.

    Attributes:
        candidates: Articles whose two layers passed DoD in the operational database.
        unchanged: Candidates already in the master with the same source fingerprint.
        held: Candidates rejected earlier with the same source fingerprint, not re-validated.
        upserted: Records inserted or refreshed.
        rejected: Candidates that failed record validation in this pass.
        retracted: Master records removed because their source no longer passes the gate.
        urgent: Upserted records whose time sensitivity is urgent.
        dirty_days: Day partitions waiting to be written after the sync.
        rejects_file: Local JSONL file listing the new rejections, if any.
        dry_run: Whether the master was left untouched.
        reject_samples: Up to five new rejections with their reasons.
    """

    candidates: int = 0
    unchanged: int = 0
    held: int = 0
    upserted: int = 0
    rejected: int = 0
    retracted: int = 0
    urgent: int = 0
    dirty_days: int = 0
    rejects_file: str | None = None
    dry_run: bool = False
    reject_samples: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert the result to a dict for logging.

        Returns:
            Dict of the fields.
        """
        return asdict(self)


def research_dir() -> Path:
    """Return the local working directory of the production publisher.

    Returns:
        Path `<data_root>/research_db`, outside any synced folder.
    """
    return paths.data_root() / "research_db"


def master_path() -> Path:
    """Return the path of the local master database.

    Returns:
        Path `<data_root>/research_db/news_research_master.db`.
    """
    return research_dir() / "news_research_master.db"


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Apply idempotent column and index migrations to an existing master database.

    Args:
        conn: Open read-write SQLite connection.
    """
    existing = {r[1] for r in conn.execute("PRAGMA table_info(article_entities)")}
    migrations = (
        ("scope", "TEXT NOT NULL DEFAULT 'title'"),
        ("role", "TEXT NOT NULL DEFAULT 'primary'"),
        ("provenance", "TEXT NOT NULL DEFAULT 'BOTH'"),
        ("confidence_tier", "TEXT NOT NULL DEFAULT 'HIGH'"),
        ("first_para_idx", "INTEGER"),
    )
    for col, spec in migrations:
        if col not in existing:
            conn.execute(f"ALTER TABLE article_entities ADD COLUMN {col} {spec}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ae_entity_role "
        "ON article_entities(entity_id, role, provenance)"
    )


def open_master(path: Path | None = None) -> sqlite3.Connection:
    """Open the local master database, creating or migrating the schema when needed.

    Args:
        path: Master database path; defaults to `master_path()`.

    Returns:
        Read-write connection in WAL mode with foreign keys on.
    """
    path = path or master_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_DDL)
    _migrate_schema(conn)
    conn.commit()
    return conn


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    """Read one value from the `_meta` table.

    Args:
        conn: Master connection.
        key: Meta key.
        default: Value returned when the key is missing.

    Returns:
        Stored value or the default.
    """
    row = conn.execute("SELECT value FROM _meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Write one value into the `_meta` table without committing.

    Args:
        conn: Master connection.
        key: Meta key.
        value: Value to store.
    """
    conn.execute("INSERT OR REPLACE INTO _meta VALUES (?, ?)", (key, value))


def mark_dirty(conn: sqlite3.Connection, days: Iterable[str | None]) -> None:
    """Queue day partitions for rewriting, without committing.

    Args:
        conn: Master connection.
        days: Days as YYYY-MM-DD; empty values are ignored.
    """
    conn.executemany("INSERT OR IGNORE INTO _dirty_days VALUES (?)",
                     [(d,) for d in set(days) if d])


def dirty_days(conn: sqlite3.Connection) -> list[str]:
    """List day partitions waiting to be written.

    Args:
        conn: Master connection.

    Returns:
        Days as YYYY-MM-DD in ascending order.
    """
    return [r[0] for r in conn.execute("SELECT day FROM _dirty_days ORDER BY day")]


def _master_state(conn: sqlite3.Connection) -> dict[str, tuple[tuple[int, int], str | None]]:
    """List the source fingerprint and partition day of every record in the master.

    Args:
        conn: Master connection.

    Returns:
        Dict article_id -> ((agent_outputs.id, l1_outputs.id), published_date).
    """
    return {r[0]: ((r[1], r[2]), r[3]) for r in conn.execute(
        "SELECT article_id, src_agent_output_id, src_l1_output_id, published_date FROM articles")}


def _write_rejects(rejections: list[gate.Rejection]) -> str | None:
    """Append new rejections to the local daily JSONL log.

    Args:
        rejections: Rejected candidates.

    Returns:
        Path of the log written, or None when there is nothing to write.
    """
    if not rejections:
        return None
    out = research_dir() / "rejects" / f"{date.today().isoformat()}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    ts = now_vn_iso()
    with open(out, "a", encoding="utf-8") as fh:
        for r in rejections:
            fh.write(json.dumps({"at": ts, "article_id": r.article_id, "reasons": r.reasons},
                                ensure_ascii=False) + "\n")
    return str(out)


def sync_master(ops_db: Path, master_db: Path | None = None, *, dry_run: bool = False,
                max_retract_ratio: float | None = None) -> SyncResult:
    """Run the validation gate over the operational database and apply the result to the master.

    Only candidates whose fingerprint changed are loaded and validated; a candidate rejected
    earlier is retried only once its source fingerprint changes. Every day partition touched by
    an upsert or a retraction, old and new day alike, is queued in `_dirty_days`. When
    retractions exceed `max_retract_ratio` of the master the sync aborts, since that pattern
    indicates a wrong or restored operational DB.

    Args:
        ops_db: Operational database, opened read-only.
        master_db: Master database path; defaults to `master_path()`.
        dry_run: If True, compute the result without writing the master or the reject log.
        max_retract_ratio: Highest share of master records one sync may retract; defaults to
            `DEFAULT_MAX_RETRACT_RATIO`.

    Returns:
        SyncResult.

    Raises:
        FileNotFoundError: If the operational database does not exist.
        RetractionGuardError: If the retraction share exceeds the guard.
    """
    if max_retract_ratio is None:
        max_retract_ratio = DEFAULT_MAX_RETRACT_RATIO
    if not Path(ops_db).is_file():
        raise FileNotFoundError(f"Không thấy DB vận hành {ops_db}.")
    src = sqlite3.connect(f"file:{Path(ops_db).as_posix()}?mode=ro", uri=True, timeout=60)
    master = open_master(master_db)
    try:
        passing = gate.passing_fingerprints(src)
        current = _master_state(master)
        held = {r[0]: (r[1], r[2]) for r in master.execute(
            "SELECT article_id, src_agent_output_id, src_l1_output_id FROM _rejects")}
        changed = [(a, fp) for a, fp in passing.items()
                   if (current.get(a) or (None,))[0] != fp and held.get(a) != fp]
        n_held = sum(1 for a, fp in passing.items()
                     if (current.get(a) or (None,))[0] != fp and held.get(a) == fp)
        retract = [a for a in current if a not in passing]
        if current and len(retract) > max_retract_ratio * len(current):
            raise RetractionGuardError(
                f"Sync sẽ rút {len(retract)}/{len(current)} bài khỏi production, vượt ngưỡng "
                f"{max_retract_ratio:.0%}. Kiểm tra lại DB vận hành trước khi chạy tiếp.")
        accepted, rejected = gate.load_and_validate(src, changed)
        changed_fp = dict(changed)
        res = SyncResult(candidates=len(passing),
                         unchanged=len(passing) - len(changed) - n_held, held=n_held,
                         upserted=len(accepted), rejected=len(rejected), retracted=len(retract),
                         urgent=sum(1 for a in accepted
                                    if a.values["time_sensitivity"] == "urgent"),
                         dry_run=dry_run,
                         reject_samples=[{"article_id": r.article_id, "reasons": r.reasons}
                                         for r in rejected[:5]])
        if dry_run:
            res.dirty_days = len(dirty_days(master))
            return res

        synced_at = now_vn_iso()
        with master:
            mark_dirty(master, [current[a][1] for a in retract])
            for aid in retract:
                master.execute("DELETE FROM articles WHERE article_id = ?", (aid,))
            master.executemany(
                "INSERT OR REPLACE INTO _rejects VALUES (?, ?, ?, ?, ?)",
                [(r.article_id, *changed_fp[r.article_id],
                  json.dumps(r.reasons, ensure_ascii=False), synced_at) for r in rejected])
            for rec in accepted:
                old_day = (current.get(rec.article_id) or (None, None))[1]
                mark_dirty(master, [old_day, rec.values["published_date"]])
                master.execute("DELETE FROM _rejects WHERE article_id = ?", (rec.article_id,))
                master.execute("DELETE FROM article_entities WHERE article_id = ?",
                               (rec.article_id,))
                is_new_article = rec.article_id not in current
                master.execute(_UPSERT_SQL, {**rec.values, "synced_at": synced_at})
                master.executemany(
                    "INSERT INTO article_entities "
                    "(article_id, ordinal, surface, entity_id, type, method, in_list, confidence, "
                    "scope, role, provenance, confidence_tier, first_para_idx) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [(rec.article_id, i, e.surface, e.entity_id, e.type, e.method,
                      int(e.in_list), e.confidence, e.scope, e.role, e.provenance,
                      e.confidence_tier, e.first_para_idx)
                     for i, e in enumerate(rec.entities)])
                if is_new_article and rec.unlisted_candidates:
                    seen_norms: set[str] = set()
                    for cand in rec.unlisted_candidates:
                        sample = cand.strip()
                        norm = sample.lower()
                        if not norm or norm in seen_norms:
                            continue
                        seen_norms.add(norm)
                        master.execute(
                            "INSERT INTO entity_candidates_log "
                            "(surface_norm, surface_sample, article_count, first_seen_at, last_seen_at, sample_article_id) "
                            "VALUES (?, ?, 1, ?, ?, ?) "
                            "ON CONFLICT(surface_norm) DO UPDATE SET "
                            "article_count = entity_candidates_log.article_count + 1, "
                            "last_seen_at = excluded.last_seen_at, "
                            "sample_article_id = excluded.sample_article_id",
                            (norm, sample, synced_at, synced_at, rec.article_id),
                        )
            set_meta(master, "last_sync_at", synced_at)
        res.dirty_days = len(dirty_days(master))
        res.rejects_file = _write_rejects(rejected)
        return res
    finally:
        src.close()
        master.close()
