"""Publish gated articles to the production news lakehouse on FRA - Data/news as daily Parquet partitions (ADR-0030)."""

# The production folder holds data only, in the ADR-0023 lakehouse layout the
# fpts-market-intel plugin already reads:
#
#   parquet/articles/year=YYYY/month=MM/part-YYYYMMDD.parquet   28-column OBT, ZSTD (ADR-0033)
#   _manifest/latest.json                                      every partition with rows, size, SHA256
#
# A publish runs the validation gate into the local master, rewrites only the day partitions the
# gate touched (identical bytes are skipped, so an unchanged day never syncs), and writes the
# manifest last. Locks, logs, rejects and state stay in `<data_root>/research_db`.

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.core import paths
from src.core.models import VN_TZ, now_vn_iso
from src.lakehouse.ingest import (LAKEHOUSE_ARTICLE_SCHEMA, published_precision,
                                  records_to_parquet_bytes)
from src.lakehouse.storage import LocalOneDriveStorageAdapter
from src.research_db import master as master_mod
from src.research_db.gate import GATE_VERSION

TARGET_ENV = "NEWS_SCAPE_RESEARCH_DB_DIR"
TARGET_FOLDER_NAME = "news"
MANIFEST = "_manifest/latest.json"
CATALOG = "_catalog/entities.json"  # the entity catalog the article prefix is built from (issue #8)
MANIFEST_SCHEMA = "news-research-production/1"
OBT_SCHEMA = "obt/2"  # obt/2 adds the ADR-0033 point-in-time and story columns
PARTITION_GLOB = "parquet/articles/*/*/*.parquet"
_PART_RE = re.compile(r"^parquet/articles/year=(\d{4})/month=(\d{2})/part-(\d{4})(\d{2})(\d{2})\.parquet$")


class PublishError(RuntimeError):
    """Raised when a publish cannot start."""


@dataclass
class PublishOutcome:
    """Result of one production publish.

    Attributes:
        status: published, unchanged, dry_run or failed.
        reason: Trigger, for example `slot:sau-phien`, `express` or `manual`.
        message: Short description.
        target: Production folder.
        written: Partitions rewritten.
        deleted: Partitions removed because their day no longer holds any article.
        failed: Partitions left dirty for the next publish, with the error.
        sync: Gate sync result.
        articles: Articles in production after the publish.
    """

    status: str
    reason: str
    message: str
    target: str | None = None
    written: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    sync: dict[str, Any] | None = None
    articles: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the outcome to a dict for logging.

        Returns:
            Dict of the fields.
        """
        return asdict(self)


def resolve_target(override: str | Path | None = None) -> Path:
    """Resolve and check the production folder.

    Args:
        override: Folder used instead of `NEWS_SCAPE_RESEARCH_DB_DIR`.

    Returns:
        Absolute folder path.

    Raises:
        PublishError: If unset, not named `news`, or inside the operational data root.
    """
    raw = str(override) if override else os.environ.get(TARGET_ENV, "").strip()
    if not raw:
        raise PublishError(f"Chưa đặt {TARGET_ENV} (thư mục FRA - Data\\news).")
    tgt = Path(raw).expanduser().absolute()
    if tgt.name.lower() != TARGET_FOLDER_NAME:
        raise PublishError(f"Đích {tgt} phải là thư mục tên '{TARGET_FOLDER_NAME}'.")
    root = paths.data_root()
    if tgt == root or root in tgt.parents:
        raise PublishError(f"Đích {tgt} nằm trong thư mục dữ liệu vận hành {root}.")
    return tgt


def partition_path(day: str) -> str:
    """Return the partition path of a day.

    Args:
        day: Day as YYYY-MM-DD.

    Returns:
        Relative path with forward slashes.
    """
    y, m, d = day[:4], day[5:7], day[8:10]
    return f"parquet/articles/year={y}/month={m}/part-{y}{m}{d}.parquet"


def _split_symbols(raw: str | None) -> list[str]:
    """Split the scraper `symbols` column into ticker codes.

    Args:
        raw: Comma-separated codes.

    Returns:
        Upper-case codes without blanks.
    """
    return [s.strip().upper() for s in (raw or "").split(",") if s.strip()]


def day_records(conn: sqlite3.Connection, day: str) -> list[dict[str, Any]]:
    """Build the OBT records of one day from the master.

    Entity fields follow the sandbox publisher: `entities` holds `<entity_id> [<type>]`, which
    the plugin parses into `article_entities`; catalog entities count as code-matchable.
    Point-in-time fields (ADR-0033): `first_seen_at` is the capture time, `analyzed_at` the
    analysis time, and `published_at_precision` is computed from the source value before
    the capture-time fallback fills `published_at`.

    Args:
        conn: Master connection.
        day: Day as YYYY-MM-DD.

    Returns:
        Records ordered by publish time descending, then article id.
    """
    ents: dict[str, list[tuple]] = defaultdict(list)
    for aid, eid, etype, in_list, role, prov in conn.execute(
            "SELECT e.article_id, e.entity_id, e.type, e.in_list, e.role, e.provenance "
            "FROM article_entities e "
            "JOIN articles a ON a.article_id = e.article_id WHERE a.published_date = ? "
            "ORDER BY e.article_id, e.ordinal", (day,)):
        if eid:
            prov_val = prov or ("BOTH" if in_list else "LLM_ONLY")
            role_val = role or ("mentioned" if prov_val == "CODE_ONLY" else "primary")
            ents[aid].append((eid, etype, bool(in_list), role_val, prov_val))
    out = []
    for r in conn.execute(
            "SELECT a.article_id, a.url, a.title, a.source_domain, a.published_at, a.fetched_at, "
            "a.summary, a.key_points_json, a.implication, a.sentiment, a.time_sensitivity, "
            "a.citations_json, a.symbols, a.categories, a.raw_sha256, a.analysis_provider, "
            "a.analysis_at, a.entity_source, s.story_id, s.story_role, s.n_sources "
            "FROM articles a LEFT JOIN article_story s ON s.article_id = a.article_id "
            "WHERE a.published_date = ? "
            "ORDER BY COALESCE(a.published_at, a.fetched_at) DESC, a.article_id", (day,)):
        (aid, url, title, domain, pub, fetched, summary, kp, implication, sentiment, ts, cit,
         symbols, categories, raw_sha, provider, analysis_at, entity_source,
         story_id, story_role, n_sources) = r
        e = ents.get(aid, [])
        llm = list(dict.fromkeys(x[0] for x in e if x[4] in ("BOTH", "LLM_ONLY")))
        code = list(dict.fromkeys(x[0] for x in e if x[4] in ("BOTH", "CODE_ONLY")))
        prov_counts: dict[str, int] = {}
        for x in e:
            prov_counts[x[4]] = prov_counts.get(x[4], 0) + 1
        intent_src_str = (
            "; ".join(f"{k}:{v}" for k, v in sorted(prov_counts.items()))
            if prov_counts
            else (entity_source or "agent")
        )
        out.append({
            "article_id": aid, "url": url, "title": title, "source_domain": domain or "",
            "published_at": pub or fetched or day, "updated_at": analysis_at or fetched or day,
            "dev_id": provider or "news_scape", "batch_id": f"b_{day.replace('-', '')}",
            "summary": summary, "key_points": json.loads(kp), "implication": implication,
            "sentiment": sentiment, "time_sensitivity": ts, "citations": json.loads(cit),
            "entities": [f"{x[0]} [{x[1]}|{x[3]}|{x[4]}]" for x in e],
            "symbols": _split_symbols(symbols),
            "categories": categories or "", "intent_llm": "; ".join(llm),
            "intent_code": "; ".join(code), "intent_source": intent_src_str,
            "gold_status": "GOLD", "raw_sha256": raw_sha or "",
            "first_seen_at": fetched, "published_at_precision": published_precision(pub),
            "analyzed_at": analysis_at, "story_id": story_id, "story_role": story_role,
            "story_n_sources": n_sources,
        })
    return out


class LocalLock:
    """Exclusive lock file in the local working directory, reclaimed when its owner process is gone.

    Attributes:
        path: Lock file path on the local filesystem.
    """

    def __init__(self, path: Path | None = None) -> None:
        """Initialize the local lock manager.

        Args:
            path: Lock file path; defaults to `<research_dir>/publish.lock`.
        """
        self.path = path or master_mod.research_dir() / "publish.lock"

    def __enter__(self) -> "LocalLock":
        """Acquire the exclusive lock file or reclaim a stale lock.

        Returns:
            Active `LocalLock` instance.

        Raises:
            PublishError: If another live publish process holds the lock or creation fails.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                if self._owner_alive():
                    raise PublishError(f"Đang có tiến trình publish khác ({self.path}).")
                self.path.unlink(missing_ok=True)
        raise PublishError(f"Không lấy được khóa {self.path}.")

    def _owner_alive(self) -> bool:
        """Report whether the process recorded in the lock file still runs.

        Returns:
            True when the owner pid exists.
        """
        import psutil

        try:
            pid = int(self.path.read_text().strip() or 0)
        except (OSError, ValueError):
            return False
        return pid > 0 and psutil.pid_exists(pid)

    def __exit__(self, *exc: object) -> None:
        """Release the lock file on context exit.

        Args:
            *exc: Exception tuple supplied by the context manager protocol.
        """
        self.path.unlink(missing_ok=True)


def _heal(conn: sqlite3.Connection, storage: LocalOneDriveStorageAdapter) -> None:
    """Queue days whose partition at the target is missing, resized or unknown to the index.

    Covers a deleted or partly restored production folder and stray partitions left by another
    writer; size is compared with a stat call, so no file is re-read.

    Args:
        conn: Master connection.
        storage: Production storage adapter.
    """
    indexed = {p: (d, s) for p, d, s in conn.execute("SELECT path, day, size FROM _partitions")}
    days = []
    for p, (d, size) in indexed.items():
        loc = storage.get_local_path(p)
        if not loc.is_file() or loc.stat().st_size != size:
            days.append(d)
    for p in storage.list_files(PARTITION_GLOB):
        m = _PART_RE.match(p)
        if p not in indexed and m:
            days.append(f"{m.group(3)}-{m.group(4)}-{m.group(5)}")
    master_mod.mark_dirty(conn, days)


def freshness(conn: sqlite3.Connection, ops_db: Path | None = None,
              backlog_hours: float = 48.0) -> dict[str, Any]:
    """Describe how fresh the published data is, for the manifest (ADR-0033).

    Args:
        conn: Master connection.
        ops_db: Operational database, opened read-only, used to count captured articles that
            are not published yet; None skips the count.
        backlog_hours: Capture window of the unpublished count.

    Returns:
        Dict with the newest publication, capture and analysis times, the share of articles
        whose source gave only a date, and the unpublished capture count of the window.
    """
    newest_pub, newest_seen, newest_analysis, n_all, n_date_only = conn.execute(
        "SELECT MAX(published_at), MAX(fetched_at), MAX(analysis_at), COUNT(*), "
        "SUM(CASE WHEN published_at IS NULL OR length(published_at) < 16 "
        "OR substr(published_at, 12, 8) IN ('00:00:00', '00:00') THEN 1 ELSE 0 END) "
        "FROM articles").fetchone()
    out: dict[str, Any] = {
        "newest_published_at": newest_pub, "newest_first_seen_at": newest_seen,
        "newest_analyzed_at": newest_analysis,
        "date_only_share": round((n_date_only or 0) / n_all, 4) if n_all else None,
        "unpublished_captured": None, "unpublished_window_hours": backlog_hours,
    }
    if ops_db is not None and Path(ops_db).is_file():
        since = (datetime.now(VN_TZ) - timedelta(hours=backlog_hours)).isoformat(timespec="seconds")
        try:
            src = sqlite3.connect(f"file:{Path(ops_db).as_posix()}?mode=ro", uri=True, timeout=30)
            try:
                captured = {r[0] for r in src.execute(
                    "SELECT url_title_hash FROM articles WHERE fetched_at >= ?", (since,))}
            finally:
                src.close()
            published = {r[0] for r in conn.execute(
                "SELECT article_id FROM articles WHERE fetched_at >= ?", (since,))}
            out["unpublished_captured"] = len(captured - published)
        except sqlite3.Error:
            pass
    return out


def _publish_catalog(storage: LocalOneDriveStorageAdapter,
                     source: Path | None = None) -> tuple[dict[str, Any] | None, bool]:
    """Copy the live entity catalog next to the partitions when its content changed.

    Consumers that rebuild or check the article prefix need the catalog the pipeline runs
    on; the manifest records its SHA-256 so they can tell which one it is.

    Args:
        storage: Production storage adapter.
        source: Catalog file; defaults to `entities.json` under the data root.

    Returns:
        Tuple of (catalog entry for the manifest or None when there is no catalog,
        True when the file was written).
    """
    src = Path(source) if source else paths.entities_dir() / "entities.json"
    if not src.is_file():
        return None, False
    data = src.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    entry = {"path": CATALOG, "size_bytes": len(data), "sha256": digest,
             "source_modified_at": datetime.fromtimestamp(src.stat().st_mtime, VN_TZ).isoformat()}
    current = storage.get_local_path(CATALOG)
    if current is not None and current.is_file()             and hashlib.sha256(current.read_bytes()).hexdigest() == digest:
        return entry, False
    storage.write_atomic(CATALOG, data)
    return entry, True


def _write_manifest(conn: sqlite3.Connection, storage: LocalOneDriveStorageAdapter,
                    reason: str, ops_db: Path | None = None,
                    catalog: dict[str, Any] | None = None) -> int:
    """Write `_manifest/latest.json` listing every partition, after all partitions are in place.

    Args:
        conn: Master connection.
        storage: Production storage adapter.
        reason: Trigger of the publish.
        ops_db: Operational database for the freshness block; None leaves the backlog unset.
        catalog: Entity catalog entry from `_publish_catalog`; None omits the block.

    Returns:
        Number of articles listed.
    """
    files = [{"path": p, "day": d, "rows": r, "size_bytes": s, "sha256": h}
             for p, d, r, s, h in conn.execute(
                 "SELECT path, day, rows, size, sha256 FROM _partitions ORDER BY day")]
    total = sum(f["rows"] for f in files)
    data = {"schema": MANIFEST_SCHEMA, "updated_at": now_vn_iso(), "trigger": reason,
            "gate_version": GATE_VERSION, "total_unique_articles": total,
            "total_partitions": len(files), "date_from": files[0]["day"] if files else None,
            "date_to": files[-1]["day"] if files else None,
            "obt_schema": OBT_SCHEMA, "columns": [f.name for f in LAKEHOUSE_ARTICLE_SCHEMA],
            "freshness": freshness(conn, ops_db), "catalog": catalog, "files": files}
    storage.write_atomic(MANIFEST, json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))
    return total


def publish(ops_db: Path, *, target: str | Path | None = None, master_db: Path | None = None,
            reason: str = "manual", dry_run: bool = False, rebuild: bool = False) -> PublishOutcome:
    """Run the gate and rewrite the changed day partitions in the production folder.

    Args:
        ops_db: Operational database.
        target: Production folder override.
        master_db: Local master override.
        reason: Trigger recorded in the manifest and the outcome.
        dry_run: Run the gate without writing anything.
        rebuild: Queue every day in the master before writing.

    Returns:
        PublishOutcome; errors are returned with status failed, never raised.
    """
    try:
        tgt = resolve_target(target)
    except PublishError as exc:
        return PublishOutcome("failed", reason, str(exc))
    try:
        with LocalLock():
            sync = master_mod.sync_master(ops_db, master_db, dry_run=dry_run).to_dict()
            if dry_run:
                return PublishOutcome("dry_run", reason, "Chạy thử cổng kiểm nghiệm, chưa ghi gì.",
                                      str(tgt), sync=sync)
            storage = LocalOneDriveStorageAdapter(tgt, allow_official=True, strict=True)
            conn = master_mod.open_master(master_db)
            try:
                if rebuild:
                    master_mod.mark_dirty(conn, [r[0] for r in conn.execute(
                        "SELECT DISTINCT published_date FROM articles")])
                _heal(conn, storage)
                conn.commit()
                out = PublishOutcome("unchanged", reason, "", str(tgt), sync=sync)
                for day in master_mod.dirty_days(conn):
                    rel = partition_path(day)
                    try:
                        recs = day_records(conn, day)
                        if recs:
                            data = records_to_parquet_bytes(recs, dev_id="production",
                                                            batch_id=f"b_{day}",
                                                            schema=LAKEHOUSE_ARTICLE_SCHEMA)
                            before = storage.get_local_path(rel)
                            unchanged = before.is_file() and before.stat().st_size == len(data) \
                                and hashlib.sha256(before.read_bytes()).hexdigest() \
                                == hashlib.sha256(data).hexdigest()
                            storage.write_atomic(rel, data)
                            conn.execute("INSERT OR REPLACE INTO _partitions VALUES (?, ?, ?, ?, ?, ?)",
                                         (rel, day, len(recs), len(data),
                                          hashlib.sha256(data).hexdigest(), now_vn_iso()))
                            if not unchanged:
                                out.written.append(rel)
                        else:
                            if storage.delete(rel):
                                out.deleted.append(rel)
                            conn.execute("DELETE FROM _partitions WHERE path = ?", (rel,))
                        conn.execute("DELETE FROM _dirty_days WHERE day = ?", (day,))
                        conn.commit()
                    except OSError as exc:
                        out.failed.append(f"{rel}: {exc}")
                catalog, catalog_written = _publish_catalog(storage)
                manifest_missing = not storage.exists(MANIFEST)
                if out.written or out.deleted or manifest_missing or catalog_written:
                    out.articles = _write_manifest(conn, storage, reason, ops_db, catalog)
                    master_mod.set_meta(conn, "last_publish_at", now_vn_iso())
                    conn.commit()
                    out.status = "published"
                else:
                    out.articles = conn.execute("SELECT COALESCE(SUM(rows), 0) FROM _partitions"
                                                ).fetchone()[0]
            finally:
                conn.close()
            if out.failed:
                out.status = "failed" if not (out.written or out.deleted) else "published"
            out.message = (f"{out.status}: ghi {len(out.written)}, xóa {len(out.deleted)}, "
                           f"lỗi {len(out.failed)} phân vùng; production {out.articles} bài "
                           f"(+{sync['upserted']} qua cổng, -{sync['retracted']} rút).")
            return out
    except Exception as exc:  # noqa: BLE001
        return PublishOutcome("failed", reason, f"{type(exc).__name__}: {exc}", str(tgt))


def urgent_since(ops_db: Path, since_iso: str) -> int:
    """Count urgent analyses that passed DoD after a time, to trigger an express publish.

    Args:
        ops_db: Operational database, opened read-only.
        since_iso: ISO time in Vietnam time, same format as `agent_outputs.created_at`.

    Returns:
        Number of urgent DoD-passed analyses created after `since_iso`.
    """
    conn = sqlite3.connect(f"file:{Path(ops_db).as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM agent_outputs WHERE dod_pass = 1 AND created_at > ? AND "
            "COALESCE(json_extract(output_json, '$.time_sensitivity'), "
            "json_extract(output_json, '$.ts')) IN ('urgent', 'urg')", (since_iso,)).fetchone()[0]
    finally:
        conn.close()


def urgent_digest(since_iso: str | None, *, master_db: Path | None = None, now=None,
                  max_age_hours: float = 12.0, limit: int = 8) -> tuple[str | None, str | None]:
    """Build one alert text for urgent stories that reached production after a watermark.

    Only the model label `time_sensitivity = urgent` selects an article; no keyword rule
    is applied (AGENTS.md section 7.3). Articles are grouped by `story_id`, so copies of
    one story produce one line. An article older than `max_age_hours` by capture time is
    skipped, so a re-analysis of old articles does not alert again.

    Args:
        since_iso: Watermark on `synced_at`; None means no watermark yet.
        master_db: Master database override.
        now: Reference time.
        max_age_hours: Oldest capture age that may still alert.
        limit: Most stories listed in one alert.

    Returns:
        (alert text or None when nothing qualifies, new watermark or the old one).
    """
    now = now or datetime.now(VN_TZ)
    fresh_from = (now - timedelta(hours=max_age_hours)).isoformat(timespec="seconds")
    conn = master_mod.open_master(master_db)
    try:
        rows = conn.execute(
            "SELECT a.article_id, a.title, a.source_domain, COALESCE(a.published_at, a.fetched_at), "
            "a.implication, a.synced_at, COALESCE(s.story_id, a.article_id), s.n_sources "
            "FROM articles a LEFT JOIN article_story s ON s.article_id = a.article_id "
            "WHERE a.time_sensitivity = 'urgent' AND a.synced_at > ? AND a.fetched_at >= ? "
            "ORDER BY COALESCE(a.published_at, a.fetched_at)",
            (since_iso or "", fresh_from)).fetchall()
        if not rows:
            return None, since_iso
        watermark = max(r[5] for r in rows)
        stories: dict[str, tuple] = {}
        for r in rows:
            stories.setdefault(r[6], r)
        lines = []
        for aid, title, domain, pub, implication, _, _, n_src in list(stories.values())[:limit]:
            tickers = [t for (t,) in conn.execute(
                "SELECT DISTINCT entity_id FROM article_entities WHERE article_id = ? "
                "AND role = 'primary' AND provenance <> 'CODE_ONLY' AND entity_id LIKE 'TICKER:%' "
                "ORDER BY ordinal LIMIT 4", (aid,))]
            tag = f" [{', '.join(t.split(':', 1)[1] for t in tickers)}]" if tickers else ""
            src = f", {n_src} nguồn" if n_src and n_src > 1 else ""
            lines.append(f"- {(pub or '')[11:16]} {title}{tag} ({domain}{src})\n"
                         f"  {implication[:220]}")
    finally:
        conn.close()
    more = len(stories) - len(lines)
    head = f"{len(stories)} câu chuyện khẩn vừa lên production:"
    tail = [f"... và {more} câu chuyện khác."] if more > 0 else []
    text = "\n".join([head, *lines, *tail])
    return text, watermark


def verify(target: str | Path | None = None, master_db: Path | None = None) -> dict[str, Any]:
    """Re-hash every production partition against the master index and the manifest.

    Args:
        target: Production folder override.
        master_db: Local master override.

    Returns:
        Dict with counts, mismatches, strays and the manifest summary.
    """
    tgt = resolve_target(target)
    conn = master_mod.open_master(master_db)
    try:
        indexed = {p: h for p, h in conn.execute("SELECT path, sha256 FROM _partitions")}
        pending = master_mod.dirty_days(conn)
    finally:
        conn.close()
    bad, missing = [], []
    for p, h in indexed.items():
        f = tgt / p
        if not f.is_file():
            missing.append(p)
        elif hashlib.sha256(f.read_bytes()).hexdigest() != h:
            bad.append(p)
    on_disk = {p.relative_to(tgt).as_posix() for p in tgt.glob(PARTITION_GLOB)}
    extra = sorted(p for p in tgt.rglob("*") if p.is_file()
                   and p.relative_to(tgt).as_posix() not in on_disk
                   and p.relative_to(tgt).as_posix() != MANIFEST and p.name != "desktop.ini")
    manifest = {}
    try:
        manifest = json.loads((tgt / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {"target": str(tgt), "partitions": len(indexed), "missing": missing,
            "sha_mismatch": bad, "strays": sorted(on_disk - set(indexed)),
            "non_data_files": [p.relative_to(tgt).as_posix() for p in extra],
            "dirty_days_pending": pending,
            "manifest": {k: manifest.get(k) for k in ("updated_at", "trigger",
                                                      "total_unique_articles", "date_to")},
            "ok": not (bad or missing or extra or set(on_disk) - set(indexed))}
