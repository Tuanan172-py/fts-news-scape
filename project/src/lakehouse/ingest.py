"""Publish article data batches into the lock-free Dropzone."""

from __future__ import annotations

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
    ]
)


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

    return {
        "article_id": str(record.get("article_id") or "").strip(),
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
        "sentiment": str(record.get("sentiment") or "neutral").strip().lower(),
        "time_sensitivity": str(record.get("time_sensitivity") or "today").strip().lower(),
        "citations": _normalize_string_list(record.get("citations")),
        "entities": _normalize_string_list(record.get("entities")),
        "symbols": clean_symbols,
        "categories": str(record.get("categories") or "").strip(),
        "intent_llm": str(record.get("intent_llm") or "").strip(),
        "intent_code": str(record.get("intent_code") or "").strip(),
        "intent_source": str(record.get("intent_source") or "").strip(),
        "gold_status": str(record.get("gold_status") or "GOLD").strip(),
        "raw_sha256": str(record.get("raw_sha256") or "").strip(),
    }


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
    filename = f"part-{yyyymmdd}-{dev_id}-{batch_id}.parquet"
    rel_path = f"{base_dir}/{year}/{month}/{day}/{filename}"

    parquet_bytes = records_to_parquet_bytes(records, dev_id=dev_id, batch_id=batch_id)
    saved_path = storage.write_atomic(rel_path, parquet_bytes)
    return saved_path
