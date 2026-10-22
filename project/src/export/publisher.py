"""Publish the data of one closed day one-way to a SharePoint folder (ADR 0023)."""

# The publish target is the environment variable `NEWS_SCAPE_PUBLISH_DIR`. When it is
# unset the publisher is off (level L0) and writes nothing. Every file is built in
# `paths.publish_staging_dir()` and then copied to the target through the protocol
# `.<name>.partial` -> fsync -> `os.replace`, never overwriting an existing file.
#
# Layout under the target:
#
# - `review/monocle_review_<YYYYMMDD>.db`: `VACUUM INTO` copy of the operational database.
# - `parquet/<table>/year=YYYY/month=MM/part-<YYYYMMDD>.parquet`: `articles`, `analysis`, `mentions`.
# - `bronze/YYYY/MM/DD/<source>.tar.xz`: raw HTML and `.meta.json` of the day.
# - `users/output/<user>/<YYYY-MM-DD>.xlsx`: delivery file of the day.
# - `_manifest/<YYYYMMDD>.json` (later revisions `<YYYYMMDD>.r<n>.json`) and `_manifest/latest.json`.

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import tarfile
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.agent.article_contract import not_code_first_sql
from src.core import paths
from src.db.connect import open_ro

PUBLISH_DIR_ENV = "NEWS_SCAPE_PUBLISH_DIR"
OFFICIAL_TARGET_MARKERS = frozenset({"fra - data"})
MANIFEST_SCHEMA = "news-scape-publish-manifest/1"
DEFAULT_KEEP_REVIEW_DAYS = 7
DEPRECATED_COLUMNS = frozenset({"materiality", "event_type", "impact_area"})
HEAVY_COLUMNS = frozenset({"content_html"})

# Parquet table -> (DB table, date column). `articles` is selected by fetch date
# (`fetched_at`); `analysis` and `mentions` by the date they passed the DoD gate
# (`created_at`). All three columns are ISO strings in Vietnam time, so the first 10
# characters are the local calendar date.
PARQUET_TABLES: dict[str, tuple[str, str]] = {
    "articles": ("articles", "fetched_at"),
    "analysis": ("agent_outputs", "created_at"),
    "mentions": ("l1_outputs", "created_at"),
}

# Extra row filter per DB table. A code-first row is not an analysis result, so it does
# not enter the `mentions` table (ADR 0010 D4).
ROW_FILTERS: dict[str, str] = {"l1_outputs": not_code_first_sql()}

_MANIFEST_RE = re.compile(r"^(\d{4}-?\d{2}-?\d{2})(?:\.r(\d+))?\.json$")
_CHUNK = 1 << 20


class PublishConflictError(RuntimeError):
    """Signal that the target file already exists with content different from the built file."""


@dataclass
class FileOutcome:
    """Result of publishing one file.

    Attributes:
        path: Relative path under the target, with forward slashes.
        kind: File kind: review, parquet, bronze, users.
        action: planned, copied, skipped, conflict or error.
        size: Size in bytes; None before the file is built.
        sha256: SHA256 hash; None before the file is built.
        rows: Row count for tabular files.
        message: Error description, if any.
        members: Members of a Bronze archive with the SHA256 of each source file.
    """

    path: str
    kind: str
    action: str = "planned"
    size: int | None = None
    sha256: str | None = None
    rows: int | None = None
    message: str = ""
    members: list[dict[str, Any]] | None = None


@dataclass
class PublishResult:
    """Result of one publish run.

    Attributes:
        status: ok, partial, failed or disabled.
        day: Publish day as YYYY-MM-DD.
        message: Short description for logs and warnings.
        target: Target directory; None when disabled.
        manifest: Relative path of the daily manifest written.
        files: Result of each file.
        pruned: Old review copies that were deleted.
    """

    status: str
    day: str
    message: str
    target: str | None = None
    manifest: str | None = None
    files: list[FileOutcome] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert the result to a dict for logging.

        Returns:
            Dict of the fields, without the Bronze member lists.
        """
        out = asdict(self)
        for f in out["files"]:
            f.pop("members", None)
        return out


def is_official_target(path: Path) -> bool:
    """Report whether the target is inside the synced folder of the official SharePoint site of the Division.

    The official site (`sites/FRA`, synced to the machine as `FRA - Data`) is not approved
    as a publish target; trial runs may only write to the sandbox `sites/FRA_DataIngestion`.
    Unlocking requires a code change with an ADR; no environment variable bypasses it.

    Args:
        path: Absolute target path.

    Returns:
        True if a path component equals the name of the synced folder of the official site.
    """
    return any(part.lower() in OFFICIAL_TARGET_MARKERS for part in path.parts)


def publish_target(override: str | Path | None = None) -> Path | None:
    """Resolve the publish target directory.

    Args:
        override: Target used instead of the environment variable for this run.

    Returns:
        Absolute target path, or None when the publisher is off or the target belongs to
        the official site.
    """
    raw = str(override) if override else os.environ.get(PUBLISH_DIR_ENV, "").strip()
    if not raw:
        return None
    tgt = Path(raw).expanduser().absolute()
    return None if is_official_target(tgt) else tgt


def sha256_file(path: Path) -> str:
    """Compute the SHA256 of a file.

    Args:
        path: File to hash.

    Returns:
        64-character hex string.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_no_overwrite(src: Path, dst: Path, sha: str | None = None) -> str:
    """Copy a file to the target through partial, fsync and replace, never overwriting.

    Args:
        src: File already built in staging.
        dst: Final path under the target.
        sha: SHA256 of `src` if already computed.

    Returns:
        `copied` when the file was just copied, `skipped` when the target already has a file with the same SHA256.

    Raises:
        PublishConflictError: If the target has a file of the same name with a different SHA256.
    """
    sha = sha or sha256_file(src)
    if dst.exists():
        if sha256_file(dst) == sha:
            return "skipped"
        raise PublishConflictError(f"{dst.name} đã có ở đích với SHA256 khác, không ghi đè.")
    dst.parent.mkdir(parents=True, exist_ok=True)
    part = dst.with_name(f".{dst.name}.partial")
    with open(src, "rb") as fin, open(part, "wb") as fout:
        shutil.copyfileobj(fin, fout, _CHUNK)
        fout.flush()
        os.fsync(fout.fileno())
    if dst.exists():
        part.unlink(missing_ok=True)
        raise PublishConflictError(f"{dst.name} xuất hiện ở đích trong lúc chép, không ghi đè.")
    os.replace(part, dst)
    return "copied"


def _write_json_replace(path: Path, data: dict[str, Any]) -> None:
    """Write JSON through a temp file and `os.replace`, for `latest.json`.

    Args:
        path: Target file.
        data: Content.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f".{path.name}.partial")
    with open(part, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(part, path)


def _now_iso() -> str:
    """Return the current Vietnam time as ISO.

    Returns:
        ISO 8601 string with the timezone.
    """
    from src.core.models import now_vn_iso

    return now_vn_iso()


def _ymd(day: date) -> str:
    """Format a date as YYYYMMDD.

    Args:
        day: Date to format.

    Returns:
        YYYYMMDD string.
    """
    return day.strftime("%Y%m%d")


# -- Read the manifests already at the target ----------------------------------

def _day_manifests(target: Path) -> dict[str, tuple[int, Path]]:
    """List the newest manifest of each day under the target.

    Args:
        target: Target directory.

    Returns:
        Dict YYYYMMDD -> (revision number, path).
    """
    out: dict[str, tuple[int, Path]] = {}
    mdir = target / "_manifest"
    if not mdir.is_dir():
        return out
    for p in mdir.iterdir():
        m = _MANIFEST_RE.match(p.name)
        if not m:
            continue
        clean_key = m.group(1).replace("-", "")
        rev = int(m.group(2) or 1)
        if clean_key not in out or rev > out[clean_key][0]:
            out[clean_key] = (rev, p)
    return out


def _load_json(path: Path) -> dict[str, Any] | None:
    """Read a JSON file, returning None when it is missing or corrupt.

    Args:
        path: JSON file.

    Returns:
        Content, or None.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _manifest_complete(target: Path, manifest: dict[str, Any]) -> bool:
    """Check that every file in the manifest is still at the target with the right size.

    Review copies may have been deleted by the keep-N policy, so they do not count.

    Args:
        target: Target directory.
        manifest: Daily manifest.

    Returns:
        True when all files are present.
    """
    for f in manifest.get("files", []):
        if f.get("kind") == "review":
            continue
        p = target / f["path"]
        if not p.is_file() or p.stat().st_size != f.get("size"):
            return False
    return True


# -- Build files in staging ----------------------------------------------------

def _plan(day: date, db: Path, include_review: bool = True,
          include_bronze: bool = True) -> list[FileOutcome]:
    """List the files to publish for a day without writing anything.

    Args:
        day: Publish day.
        db: Operational database.
        include_review: Whether to include the SQLite review snapshot in the plan.
        include_bronze: Whether to include the Bronze HTML archives in the plan.

    Returns:
        FileOutcome entries in the planned state.
    """
    ymd = _ymd(day)
    plan: list[FileOutcome] = []
    if include_review:
        plan.append(FileOutcome(f"review/monocle_review_{ymd}.db", "review"))
    plan.append(FileOutcome(f"parquet/articles/year={day:%Y}/month={day:%m}/part-{ymd}.parquet", "parquet"))
    if include_bronze:
        bronze = paths.bronze_dir()
        if bronze.is_dir():
            for src_dir in sorted(bronze.iterdir()):
                if (src_dir / ymd).is_dir() and any((src_dir / ymd).iterdir()):
                    plan.append(FileOutcome(
                        f"bronze/{day:%Y}/{day:%m}/{day:%d}/{src_dir.name}.tar.xz", "bronze"))
    users = paths.users_output_dir()
    if users.is_dir():
        for udir in sorted(users.iterdir()):
            if udir.is_dir() and not udir.name.startswith("_") \
                    and (udir / f"{day.isoformat()}.xlsx").is_file():
                plan.append(FileOutcome(f"users/output/{udir.name}/{day.isoformat()}.xlsx", "users"))
    return plan


def _build_review(db: Path, out: Path) -> None:
    """Build the review copy with `VACUUM INTO` over a read-only connection.

    Args:
        db: Operational database.
        out: Target file in staging.
    """
    from src.db.snapshot import create_db_snapshot

    final = create_db_snapshot(db, out, overwrite=True)
    if final != out.resolve():
        os.replace(final, out)


def _build_obt_parquet(db: Path, day: date, out: Path) -> int:
    """Export the articles of a day from the database to a One Big Table Parquet (22 columns).

    Args:
        db: Operational database.
        day: Publish day.
        out: Target file in staging.

    Returns:
        Number of rows written.
    """
    from src.lakehouse.ingest import LAKEHOUSE_ARTICLE_SCHEMA, records_to_parquet_bytes

    day_str = day.isoformat()
    conn = open_ro(db, timeout=30)
    query = """
    WITH day_articles AS (
        SELECT url_title_hash AS article_id, title, url, source_domain,
               published_at, fetched_at, symbols, categories
        FROM articles
        WHERE (substr(published_at, 1, 10) = ? OR ((published_at IS NULL OR published_at = '') AND substr(fetched_at, 1, 10) = ?))
    )
    SELECT a.article_id, a.title, a.url, a.source_domain,
           a.published_at, a.fetched_at, a.symbols, a.categories,
           ag.raw_sha256, ag.output_json AS agent_json, ag.agent_provider, ag.created_at AS agent_created_at,
           l1.output_json AS l1_json, l1.l1_source
    FROM day_articles a
    LEFT JOIN agent_outputs ag ON ag.id = (
        SELECT MAX(id) FROM agent_outputs WHERE article_id = a.article_id AND dod_pass = 1
    )
    LEFT JOIN l1_outputs l1 ON l1.id = (
        SELECT MAX(id) FROM l1_outputs WHERE article_id = a.article_id AND dod_pass = 1
    )
    ORDER BY a.published_at DESC
    """
    try:
        rows = conn.execute(query, (day_str, day_str)).fetchall()
    finally:
        conn.close()

    records = []
    for r in rows:
        (art_id, title, url, domain, pub_at, fetch_at, symbols, categories,
         raw_sha, ag_json_str, ag_prov, ag_created, l1_json_str, l1_src) = r

        ag = {}
        if ag_json_str:
            try:
                ag = json.loads(ag_json_str)
            except Exception:
                ag = {}

        l1 = {}
        if l1_json_str:
            try:
                l1 = json.loads(l1_json_str)
            except Exception:
                l1 = {}

        summary_val = ag.get("summary") or ag.get("s") or ""
        if isinstance(summary_val, dict):
            summary_val = summary_val.get("abstractive") or ""
        key_points = ag.get("key_points") or ag.get("k") or []
        implication_val = ag.get("implication") or ag.get("im") or ""
        if isinstance(implication_val, dict):
            implication_val = implication_val.get("text") or ""
        sentiment_val = ag.get("sentiment") or ag.get("sn") or "neutral"
        time_sens_val = ag.get("time_sensitivity") or ag.get("ts") or "today"
        citations_val = ag.get("citations") or ag.get("c") or []

        intent_llm, intent_code, intent_source = "", "", ""
        entities_list = []
        if l1:
            matched_entities = l1.get("entities") or []
            llm_ents, code_ents = [], []
            for ent in matched_entities:
                ename = ent.get("entity_id") or ent.get("name") or ""
                etype = ent.get("type") or ""
                if ename:
                    entities_list.append(f"{ename} [{etype}]" if etype else str(ename))
                src_flag = ent.get("source") or ("BOTH" if ent.get("in_list") else "LLM_ONLY")
                if src_flag in ("BOTH", "LLM_ONLY") and ename:
                    llm_ents.append(ename)
                if src_flag in ("BOTH", "CODE_ONLY") and ename:
                    code_ents.append(ename)
            intent_llm = "; ".join(dict.fromkeys(llm_ents))
            intent_code = "; ".join(dict.fromkeys(code_ents))
            intent_source = l1_src or ("BOTH" if (intent_llm and intent_code) else ("LLM_ONLY" if intent_llm else "CODE_ONLY"))

        rec = {
            "article_id": art_id,
            "url": url or "",
            "title": title or "",
            "source_domain": domain or "",
            "published_at": pub_at or fetch_at or day_str,
            "updated_at": ag_created or fetch_at or day_str,
            "dev_id": ag_prov or "news_scape",
            "batch_id": f"b_{day_str.replace('-', '')}",
            "summary": summary_val,
            "key_points": key_points,
            "implication": implication_val,
            "sentiment": sentiment_val,
            "time_sensitivity": time_sens_val,
            "citations": citations_val,
            "entities": entities_list,
            "symbols": symbols or "",
            "categories": categories or "",
            "intent_llm": intent_llm,
            "intent_code": intent_code,
            "intent_source": intent_source,
            "gold_status": "GOLD" if ag else ("L1_ONLY" if l1 else "RAW"),
            "raw_sha256": raw_sha or "",
        }
        records.append(rec)

    out.parent.mkdir(parents=True, exist_ok=True)
    parquet_bytes = records_to_parquet_bytes(
        records,
        dev_id="publisher",
        batch_id=f"b_{day_str.replace('-', '')}",
        schema=LAKEHOUSE_ARTICLE_SCHEMA,
    )
    out.write_bytes(parquet_bytes)
    return len(records)


def _build_parquet(db: Path, table: str, date_col: str, day: date, out: Path) -> int:
    """Export the rows of a day from one database table to Parquet (kept for tests and backward compatibility).

    Args:
        db: Operational database.
        table: Source table.
        date_col: Date column used to select rows.
        day: Publish day.
        out: Target file in staging.

    Returns:
        Number of rows written.

    Raises:
        RuntimeError: If the table does not exist in the database.
    """
    import pandas as pd

    conn = open_ro(db, timeout=30)
    try:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        keep = [c for c in cols if c not in HEAVY_COLUMNS and c not in DEPRECATED_COLUMNS]
        if not keep:
            raise RuntimeError(f"Bảng {table} không có trong DB.")
        extra = f" AND {ROW_FILTERS[table]}" if table in ROW_FILTERS else ""
        sql = (f"SELECT {', '.join(keep)} FROM {table} "
               f"WHERE substr({date_col}, 1, 10) = ?{extra} ORDER BY rowid")
        frame = pd.read_sql_query(sql, conn, params=(day.isoformat(),))
    finally:
        conn.close()

    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out, engine="pyarrow", index=False)
    return len(frame)


def _build_bronze(src_dir: Path, out: Path) -> list[dict[str, Any]]:
    """Compress the Bronze directory of one source for one day into `.tar.xz`.

    Members are sorted by name and ownership is set to 0, so the same input gives the same archive.

    Args:
        src_dir: Directory `<bronze>/<source>/<YYYYMMDD>`.
        out: Target file in staging.

    Returns:
        Members: name in the archive, size and SHA256 of the source file.
    """
    base = src_dir.parent.parent
    members = []
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w:xz", preset=1) as tar:
        for f in sorted(p for p in src_dir.rglob("*") if p.is_file()):
            arc = f.relative_to(base).as_posix()
            info = tar.gettarinfo(str(f), arcname=arc)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with open(f, "rb") as fh:
                tar.addfile(info, fh)
            members.append({"name": arc, "size": info.size, "sha256": sha256_file(f)})
    return members


def _build(item: FileOutcome, day: date, db: Path, stage: Path) -> None:
    """Build one file in staging and fill in its size, SHA256 and row count.

    A file already in staging from an earlier interrupted run is reused, keeping the SHA256 stable.

    Args:
        item: File to build.
        day: Publish day.
        db: Operational database.
        stage: Staging directory of the day.
    """
    out = stage / item.path
    side = out.with_name(out.name + ".info.json")
    if out.is_file() and side.is_file():
        info = _load_json(side) or {}
        item.rows, item.members = info.get("rows"), info.get("members")
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        if item.kind == "review":
            _build_review(db, out)
        elif item.kind == "parquet":
            item.rows = _build_obt_parquet(db, day, out)
        elif item.kind == "bronze":
            source = Path(item.path).name[: -len(".tar.xz")]
            item.members = _build_bronze(paths.bronze_dir() / source / _ymd(day), out)
        elif item.kind == "users":
            _, _, user, fname = item.path.split("/")
            shutil.copyfile(paths.users_output_dir() / user / fname, out)
        side.write_text(json.dumps({"rows": item.rows, "members": item.members},
                                   ensure_ascii=False), encoding="utf-8")
    item.size = out.stat().st_size
    item.sha256 = sha256_file(out)


# -- Manifest and review retention policy --------------------------------------

def _manifest_entry(item: FileOutcome) -> dict[str, Any]:
    """Build the manifest entry of a file.

    Args:
        item: File that was published.

    Returns:
        Manifest entry dict.
    """
    e: dict[str, Any] = {"path": item.path, "kind": item.kind, "size": item.size,
                         "sha256": item.sha256}
    if item.rows is not None:
        e["rows"] = item.rows
    if item.members is not None:
        e["members"] = item.members
    return e


def _prune_reviews(target: Path, keep: int) -> list[str]:
    """Delete review copies older than the N most recent days, only those the publisher wrote.

    A review copy is deleted only when the manifest of its day lists it and the SHA256 matches.

    Args:
        target: Target directory.
        keep: Number of review days to keep.

    Returns:
        Relative paths of the copies deleted.
    """
    reviews = []
    for ymd, (_, mpath) in _day_manifests(target).items():
        for f in (_load_json(mpath) or {}).get("files", []):
            if f.get("kind") == "review":
                reviews.append((ymd, f))
    reviews.sort(key=lambda t: t[0], reverse=True)
    pruned = []
    for _, f in reviews[max(keep, 1):]:
        p = target / f["path"]
        if p.is_file() and sha256_file(p) == f.get("sha256"):
            p.unlink()
            pruned.append(f["path"])
    return pruned


def _write_day_manifest(target: Path, day: date, files: list[FileOutcome],
                        existing: tuple[int, Path] | None) -> str:
    """Write the daily manifest; write a new revision when the content changed from the previous one.

    Args:
        target: Target directory.
        day: Publish day.
        files: Files already at the target.
        existing: Newest manifest of the day, if any.

    Returns:
        Relative path of the effective manifest.
    """
    entries = sorted((_manifest_entry(f) for f in files), key=lambda e: e["path"])
    if existing:
        old = _load_json(existing[1]) or {}
        old_set = {(e["path"], e.get("sha256")) for e in old.get("files", [])}
        if old_set == {(e["path"], e["sha256"]) for e in entries}:
            return f"_manifest/{existing[1].name}"
    rev = existing[0] + 1 if existing else 1
    iso_d = day.isoformat()
    name = f"{iso_d}.json" if rev == 1 else f"{iso_d}.r{rev}.json"
    data = {"schema": MANIFEST_SCHEMA, "day": iso_d, "revision": rev,
            "generated_at": _now_iso(), "host": socket.gethostname(), "files": entries}
    stage = paths.publish_staging_dir() / "_manifest"
    stage.mkdir(parents=True, exist_ok=True)
    tmp = stage / name
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    copy_no_overwrite(tmp, target / "_manifest" / name)
    tmp.unlink(missing_ok=True)
    return f"_manifest/{name}"


def _write_latest(target: Path, day: date, manifest_rel: str, pruned: list[str]) -> None:
    """Write `_manifest/latest.json` last, pointing to the newest published day.

    Args:
        target: Target directory.
        day: Day just published.
        manifest_rel: Effective manifest of the day just published.
        pruned: Review copies just deleted.
    """
    days = _day_manifests(target)
    newest = max(days)
    latest_rel = f"_manifest/{days[newest][1].name}"
    latest_day_manifest = _load_json(target / latest_rel) or {}
    parquet_files = [
        {
            "path": f["path"],
            "rows": f.get("rows", 0),
            "size_bytes": f.get("size", 0),
            "sha256": f.get("sha256", ""),
        }
        for f in latest_day_manifest.get("files", [])
        if f.get("kind") == "parquet"
    ]
    formatted_day = f"{newest[:4]}-{newest[4:6]}-{newest[6:]}" if len(newest) == 8 else newest
    data = {
        "schema": MANIFEST_SCHEMA,
        "latest_date": formatted_day,
        "manifest_ref": latest_rel,
        "updated_at": _now_iso(),
        "host": socket.gethostname(),
        "day": formatted_day,
        "manifest": latest_rel,
        "total_partitions": len(parquet_files),
        "total_unique_articles": sum(p["rows"] for p in parquet_files),
        "files": parquet_files,
        "manifests": sorted(f"_manifest/{p.name}" for _, p in days.values()),
        "last_published": {"day": day.isoformat(), "manifest": manifest_rel},
        "pruned": pruned,
    }
    _write_json_replace(target / "_manifest" / "latest.json", data)


# -- Entry points --------------------------------------------------------------

def publish_day(day: date, *, dry_run: bool = False, force: bool = False,
                target: str | Path | None = None, db_path: str | Path | None = None,
                keep_review_days: int | None = None,
                include_review: bool = True,
                include_bronze: bool = True) -> PublishResult:
    """Publish the data of one closed day to the target directory.

    A day whose manifest exists and is complete is not redone unless `force` is set. An
    interrupted earlier run resumes from files left in staging and files already at the
    target with the same SHA256. Every error is caught and returned in the result and is
    never raised.

    Args:
        day: Publish day.
        dry_run: If True, only plan the files and write nothing.
        force: If True, check and copy the missing parts even when the daily manifest is complete.
        target: Target used instead of `NEWS_SCAPE_PUBLISH_DIR` for this run.
        db_path: Operational database; defaults to `resolve_db_path()`.
        keep_review_days: Number of review copies to keep; defaults to `publish.keep_review_days`.
        include_review: Whether to include the SQLite review snapshot in the plan.
        include_bronze: Whether to include the Bronze HTML archives in the plan.

    Returns:
        PublishResult with status ok, partial, failed or disabled.
    """
    tgt = publish_target(target)
    if tgt is None:
        raw = str(target) if target else os.environ.get(PUBLISH_DIR_ENV, "").strip()
        if raw:
            return PublishResult("failed", day.isoformat(),
                                 f"Đích {raw} thuộc site SharePoint chính thức, chưa được duyệt "
                                 f"(ADR 0023). Chỉ dùng sandbox sites/FRA_DataIngestion.")
        return PublishResult("disabled", day.isoformat(),
                             f"Chưa đặt {PUBLISH_DIR_ENV}: publisher tắt (mức L0).")
    try:
        return _publish(day, tgt, dry_run=dry_run, force=force, db_path=db_path,
                        keep_review_days=keep_review_days,
                        include_review=include_review,
                        include_bronze=include_bronze)
    except Exception as exc:  # noqa: BLE001
        return PublishResult("failed", day.isoformat(), f"Xuất bản lỗi: {exc}", target=str(tgt))


def _publish(day: date, tgt: Path, *, dry_run: bool, force: bool,
             db_path: str | Path | None, keep_review_days: int | None,
             include_review: bool = True,
             include_bronze: bool = True) -> PublishResult:
    """Run the publish; `publish_day` catches its errors.

    Args:
        day: Publish day.
        tgt: Target directory.
        dry_run: Plan only.
        force: Ignore the complete-manifest condition.
        db_path: Operational database.
        keep_review_days: Number of review copies to keep.
        include_review: Whether to include the SQLite review snapshot in the plan.
        include_bronze: Whether to include the Bronze HTML archives in the plan.

    Returns:
        PublishResult.
    """
    if db_path is None:
        from src.core.config import resolve_db_path
        db_path = resolve_db_path()
    db = Path(db_path)
    if keep_review_days is None:
        from src.ops.config import load_config
        keep_review_days = int((load_config().get("publish") or {}).get(
            "keep_review_days", DEFAULT_KEEP_REVIEW_DAYS))
    iso_day = day.isoformat()
    existing = _day_manifests(tgt).get(_ymd(day)) if tgt.is_dir() else None
    old = (_load_json(existing[1]) or {}) if existing else {}
    if existing and not force and _manifest_complete(tgt, old):
        return PublishResult("ok", iso_day, f"Ngày {iso_day} đã xuất bản, không làm lại.",
                             target=str(tgt), manifest=f"_manifest/{existing[1].name}")
    plan = _plan(day, db, include_review=include_review, include_bronze=include_bronze)
    if dry_run:
        return PublishResult("ok", iso_day, f"Kế hoạch {len(plan)} tệp, chưa ghi gì.",
                             target=str(tgt), files=plan)
    if not db.is_file():
        return PublishResult("failed", iso_day, f"Không thấy DB vận hành {db}.", target=str(tgt))

    vouched = {f["path"]: f for f in old.get("files", [])}
    stage = paths.publish_staging_dir() / _ymd(day)
    done: list[FileOutcome] = []
    for item in plan:
        dst = tgt / item.path
        prior = vouched.get(item.path)
        try:
            if prior and dst.is_file() and sha256_file(dst) == prior.get("sha256"):
                # The manifest already vouches for this file: keep it and do not rebuild (a review copy changes on every build).
                item.size, item.sha256 = prior.get("size"), prior.get("sha256")
                item.rows, item.members = prior.get("rows"), prior.get("members")
                item.action = "skipped"
            else:
                _build(item, day, db, stage)
                item.action = copy_no_overwrite(stage / item.path, dst, item.sha256)
            done.append(item)
        except PublishConflictError as exc:
            item.action, item.message = "conflict", str(exc)
        except Exception as exc:  # noqa: BLE001
            item.action, item.message = "error", f"{type(exc).__name__}: {exc}"

    bad = [f for f in plan if f.action in ("conflict", "error")]
    if bad:
        status = "partial" if done else "failed"
        detail = "; ".join(f"{f.path}: {f.message}" for f in bad[:3])
        return PublishResult(status, iso_day, f"{len(bad)}/{len(plan)} tệp lỗi: {detail}",
                             target=str(tgt), files=plan)

    manifest_rel = _write_day_manifest(tgt, day, done, existing)
    pruned = _prune_reviews(tgt, keep_review_days)
    _write_latest(tgt, day, manifest_rel, pruned)
    shutil.rmtree(stage, ignore_errors=True)
    copied = sum(1 for f in plan if f.action == "copied")
    return PublishResult("ok", iso_day, f"Xuất bản {iso_day}: chép {copied}, giữ nguyên "
                         f"{len(plan) - copied} tệp.", target=str(tgt), manifest=manifest_rel,
                         files=plan, pruned=pruned)


def parse_day(text: str, today: date | None = None) -> date:
    """Parse a day argument `YYYY-MM-DD`, `today` or `yesterday`.

    Args:
        text: Day string.
        today: Today in Vietnam time; None computes it.

    Returns:
        Corresponding date.

    Raises:
        ValueError: If the string has an invalid format.
    """
    from datetime import timedelta

    from src.core.models import VN_TZ

    base = today or datetime.now(VN_TZ).date()
    if text == "today":
        return base
    if text == "yesterday":
        return base - timedelta(days=1)
    return date.fromisoformat(text)
