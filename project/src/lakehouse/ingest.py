"""Publish article data batches into the lock-free Dropzone."""

from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from src.lakehouse.storage import BaseStorageAdapter

# Standard Parquet schema for the whole Lakehouse system.
LAKEHOUSE_ARTICLE_SCHEMA = pa.schema(
    [
        ("article_id", pa.string()),
        ("url", pa.string()),
        ("title", pa.string()),
        ("source_domain", pa.string()),
        ("published_at", pa.string()),
        ("updated_at", pa.string()),
        ("dev_id", pa.string()),
        ("batch_id", pa.string()),
        ("summary", pa.string()),
        ("key_points", pa.list_(pa.string())),
        ("implication", pa.string()),
        ("sentiment", pa.string()),
        ("time_sensitivity", pa.string()),
        ("citations", pa.list_(pa.string())),
        ("entities", pa.list_(pa.string())),
        ("symbols", pa.list_(pa.string())),
        ("categories", pa.string()),
        ("intent_llm", pa.string()),
        ("intent_code", pa.string()),
        ("intent_source", pa.string()),
        ("gold_status", pa.string()),
        ("raw_sha256", pa.string()),
        # Point-in-time and story columns (ADR-0033). Older partitions lack them; readers
        # must fill NULL, which is why they are appended at the end of the schema.
        ("first_seen_at", pa.string()),
        ("published_at_precision", pa.string()),
        ("analyzed_at", pa.string()),
        ("story_id", pa.string()),
        ("story_role", pa.string()),
        ("story_n_sources", pa.int32()),
    ]
)

# Columns added by ADR-0033, in schema order.
PIT_COLUMNS = (
    "first_seen_at", "published_at_precision", "analyzed_at",
    "story_id", "story_role", "story_n_sources",
)
PUBLISHED_PRECISIONS = frozenset({"datetime", "date", "missing"})


def published_precision(published_at: str | None) -> str:
    """Classify how precise a source publication timestamp is.

    A time of exactly midnight is what date-only source pages produce after parsing, so it
    is treated as a date without a time of day.

    Args:
        published_at: ISO 8601 timestamp from the source page, or None.

    Returns:
        `missing` without a value, `date` when no time of day is known, else `datetime`.
    """
    raw = (published_at or "").strip()
    if len(raw) < 10:
        return "missing"
    time_part = raw[11:19] if len(raw) >= 16 else ""
    if not time_part or time_part in ("00:00:00", "00:00"):
        return "date"
    return "datetime"


def parse_date_components(date_str: str) -> tuple[str, str, str, str]:
    """Split a date string into year, month, day and the compact YYYYMMDD string.

    Args:
        date_str: Date string as 'YYYY-MM-DD' or 'YYYYMMDD'.

    Returns:
        Tuple of 4 elements: (year, month, day, yyyymmdd string).

    Raises:
        ValueError: If the date string format is invalid.
    """
    clean = re.sub(r"[^0-9]", "", date_str.strip())
    if len(clean) < 8:
        raise ValueError(f"Định dạng chuỗi ngày không hợp lệ: {date_str}")
    year = clean[:4]
    month = clean[4:6]
    day = clean[6:8]
    yyyymmdd = f"{year}{month}{day}"
    return year, month, day, yyyymmdd


def _normalize_string_list(val: Any) -> list[str]:
    """Normalize an input value into a list of strings.

    Args:
        val: Value to convert (list, tuple, JSON string or delimited string).

    Returns:
        List of strings with whitespace trimmed.
    """
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return [str(x).strip() for x in val if x is not None and str(x).strip()]
    if isinstance(val, str):
        raw = val.strip()
        if not raw:
            return []
        if raw.startswith("[") and raw.endswith("]"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if x is not None and str(x).strip()]
            except Exception:
                pass
        # Split by line, semicolon or comma.
        if "\n" in raw:
            return [line.lstrip("-*• ").strip() for line in raw.splitlines() if line.strip()]
        if ";" in raw:
            return [item.strip() for item in raw.split(";") if item.strip()]
        if "," in raw:
            return [item.strip() for item in raw.split(",") if item.strip()]
        return [raw]
    return [str(val)]


_TYPE_TAG = re.compile(r"\s*\[[^\]]*\]\s*$")


def _entity_id(item: str) -> str:
    return _TYPE_TAG.sub("", item).strip().upper()


def keep_model_entities(entities: list[str], intent_llm: str, intent_code: str) -> list[str]:
    """Keep only the ``entities`` items whose id the model named (ADR: model ids only in ``entities``).

    The deterministic matcher cross-checks the model and never adds results (AGENTS.md section 7), so ids it
    found alone stay visible in ``intent_code`` and leave ``entities``. Ids compare in full (``IND_GICS2`` and
    ``IND_GICS3`` share codes), with ``[TYPE]`` tags stripped; a bare code the model wrote without its kind
    (``HPG``) matches that code under any kind.

    Args:
        entities: ``KIND:CODE [TYPE]`` items as produced.
        intent_llm: ``"; "``-separated ids the model named.
        intent_code: ``"; "``-separated ids the code layer found.

    Returns:
        The model's items in their original order; ``entities`` unchanged when the row carries no provenance
        (both intent columns empty, as in records from before the intent columns existed).
    """
    if not intent_llm.strip() and not intent_code.strip():
        return entities
    named = {_entity_id(x) for x in intent_llm.split(";") if x.strip()}
    bare = {n for n in named if ":" not in n}

    def is_named(item: str) -> bool:
        eid = _entity_id(item)
        return eid in named or eid.split(":", 1)[-1] in bare

    return [e for e in entities if is_named(e)]


def sanitize_article_record(
    record: dict[str, Any],
    dev_id: str,
    batch_id: str,
    default_timestamp: str,
) -> dict[str, Any]:
    """Normalize an article record to match LAKEHOUSE_ARTICLE_SCHEMA.

    Args:
        record: Original article data dict.
        dev_id: Identifier of the Dev or Worker that publishes.
        batch_id: Article batch identifier.
        default_timestamp: Default ISO 8601 UTC timestamp.

    Returns:
        Cleaned dict with all required fields filled.
    """
    rec_dev = str(record.get("dev_id") or dev_id).strip()
    rec_batch = str(record.get("batch_id") or batch_id).strip()
    rec_updated = str(record.get("updated_at") or default_timestamp).strip()
    rec_pub = str(record.get("published_at") or default_timestamp).strip()

    raw_symbols = _normalize_string_list(record.get("symbols"))
    clean_symbols = [s.upper() for s in raw_symbols if s and s.strip()]

    raw_art_id = str(record.get("article_id") or "").strip()
    if not raw_art_id:
        ref_val = str(record.get("url") or record.get("raw_sha256") or record.get("title") or "").strip()
        if ref_val:
            raw_art_id = hashlib.sha256(ref_val.encode("utf-8")).hexdigest()[:16]

    raw_sentiment = record.get("sentiment")
    clean_sentiment = str(raw_sentiment).strip().lower() if raw_sentiment is not None and str(raw_sentiment).strip() else ""

    raw_gold = record.get("gold_status")
    clean_gold = str(raw_gold).strip() if raw_gold is not None and str(raw_gold).strip() else "RAW"

    return {
        "article_id": raw_art_id,
        "url": str(record.get("url") or "").strip(),
        "title": str(record.get("title") or "").strip(),
        "source_domain": str(record.get("source_domain") or "").strip(),
        "published_at": rec_pub,
        "updated_at": rec_updated,
        "dev_id": rec_dev,
        "batch_id": rec_batch,
        "summary": str(record.get("summary") or "").strip(),
        "key_points": _normalize_string_list(record.get("key_points")),
        "implication": str(record.get("implication") or "").strip(),
        "sentiment": clean_sentiment,
        "time_sensitivity": str(record.get("time_sensitivity") or "today").strip().lower(),
        "citations": _normalize_string_list(record.get("citations")),
        "entities": keep_model_entities(_normalize_string_list(record.get("entities")),
                                        str(record.get("intent_llm") or ""), str(record.get("intent_code") or "")),
        "symbols": clean_symbols,
        "categories": str(record.get("categories") or "").strip(),
        "intent_llm": str(record.get("intent_llm") or "").strip(),
        "intent_code": str(record.get("intent_code") or "").strip(),
        "intent_source": str(record.get("intent_source") or "").strip(),
        "gold_status": clean_gold,
        "raw_sha256": str(record.get("raw_sha256") or "").strip(),
        "first_seen_at": _opt_str(record.get("first_seen_at")),
        "published_at_precision": (
            str(record.get("published_at_precision")).strip()
            if record.get("published_at_precision") in PUBLISHED_PRECISIONS else None),
        "analyzed_at": _opt_str(record.get("analyzed_at")),
        "story_id": _opt_str(record.get("story_id")),
        "story_role": _opt_str(record.get("story_role")),
        "story_n_sources": _opt_int(record.get("story_n_sources")),
    }


def _opt_str(val: Any) -> str | None:
    """Return a stripped string, or None for an empty value.

    Args:
        val: Any value.

    Returns:
        The stripped string or None.
    """
    text = str(val).strip() if val is not None else ""
    return text or None


def _opt_int(val: Any) -> int | None:
    """Return an int, or None when the value is missing or not numeric.

    Args:
        val: Any value.

    Returns:
        The integer or None.
    """
    if val is None or isinstance(val, bool):
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def records_to_parquet_bytes(
    records: list[dict[str, Any]],
    dev_id: str,
    batch_id: str,
    schema: pa.Schema = LAKEHOUSE_ARTICLE_SCHEMA,
) -> bytes:
    """Convert article records to ZSTD-compressed Parquet bytes.

    Args:
        records: Article data dicts.
        dev_id: Identifier of the Dev or Worker that publishes.
        batch_id: Article batch identifier.
        schema: PyArrow schema applied to the table.

    Returns:
        Parquet-format bytes.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    clean_records = [
        sanitize_article_record(r, dev_id=dev_id, batch_id=batch_id, default_timestamp=now_iso)
        for r in records
    ]
    table = pa.Table.from_pylist(clean_records, schema=schema)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="ZSTD")
    return buf.getvalue()


def publish_batch(
    records: list[dict[str, Any]],
    date_str: str,
    dev_id: str,
    batch_id: str,
    storage: BaseStorageAdapter,
    base_dir: str = "dropzone",
) -> str:
    """Publish an article batch into the Dropzone as a fragment Parquet file.

    Each file name is unique within a per-worker namespace, which removes file-lock
    contention and sync conflicts between multiple Workers.

    Args:
        records: Article data dicts to publish.
        date_str: Partition date string (for example '2026-10-08' or '20261008').
        dev_id: Unique identifier of the publishing Worker/Dev (for example 'dev_anpt').
        batch_id: Data batch identifier (for example 'b01').
        storage: Storage system adapter.
        base_dir: Root directory of the dropzone.

    Returns:
        Relative path of the Parquet file that was published.

    Raises:
        ValueError: If the record list is empty or the identifiers are missing.
    """
    if not records:
        raise ValueError("Danh sách bản ghi bài viết không được để rỗng.")
    if not dev_id or not batch_id:
        raise ValueError("Mã định danh dev_id và batch_id là bắt buộc.")

    year, month, day, yyyymmdd = parse_date_components(date_str)
    base_filename = f"part-{yyyymmdd}-{dev_id}-{batch_id}"
    rel_path = f"{base_dir}/{year}/{month}/{day}/{base_filename}.parquet"
    if storage.exists(rel_path):
        ts_suffix = datetime.now(timezone.utc).strftime("%H%M%S%f")
        rel_path = f"{base_dir}/{year}/{month}/{day}/{base_filename}-{ts_suffix}.parquet"

    parquet_bytes = records_to_parquet_bytes(records, dev_id=dev_id, batch_id=batch_id)
    saved_path = storage.write_atomic(rel_path, parquet_bytes)
    return saved_path
