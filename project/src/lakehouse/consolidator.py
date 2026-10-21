"""Consolidate and deduplicate Lakehouse data with DuckDB."""

from __future__ import annotations

import hashlib
import io
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from src.lakehouse.ingest import parse_date_components
from src.lakehouse.manifest import PartitionManifestEntry, write_manifests
from src.lakehouse.storage import BaseStorageAdapter


@dataclass
class ConsolidationResult:
    """Result of consolidating and deduplicating article data.

    Attributes:
        date_str: Business date string that was processed.
        total_scanned: Total raw records scanned from the ingested files.
        unique_articles: Number of unique article records after deduplication.
        partition_file: Relative path of the resulting Parquet partition file.
        manifest_file: Relative path of the daily manifest file.
        sha256: SHA-256 hash of the Parquet partition file.
        elapsed_ms: Run time in milliseconds.
        partitions: Partition entries in the manifest.
    """

    date_str: str
    total_scanned: int
    unique_articles: int
    partition_file: str
    manifest_file: str
    sha256: str
    elapsed_ms: float
    partitions: list[PartitionManifestEntry] = field(default_factory=list)


def consolidate_dropzone(
    date_str: str,
    storage: BaseStorageAdapter,
    dropzone_pattern: str = "dropzone/*/*/*/*.parquet",
    output_base: str = "parquet/articles",
    auto_purge: bool = True,
) -> ConsolidationResult:
    """Scan the Dropzone, deduplicate by article_id and write the Parquet partition.

    Uses DuckDB with QUALIFY ROW_NUMBER() OVER (...) to prefer the record with the latest
    updated_at. Merges with the partition file that already exists so incremental
    compaction is safe.

    Args:
        date_str: Business date to consolidate (for example '2026-10-08' or '20261008').
        storage: Storage system adapter.
        dropzone_pattern: Glob pattern for the files in the Dropzone.
        output_base: Root directory of the partitioned Parquet store.
        auto_purge: Delete the consolidated Dropzone files after a successful merge.

    Returns:
        ConsolidationResult with the consolidation statistics and audit metadata.
    """
    t_start = time.perf_counter()
    year, month, day, yyyymmdd = parse_date_components(date_str)

    # Collect the files in the dropzone.
    date_specific_prefix = f"dropzone/{year}/{month}/{day}"
    all_dropzone_files = storage.list_files(dropzone_pattern)
    matched_dropzone = [
        f for f in all_dropzone_files if f.startswith(date_specific_prefix)
    ]

    # If no file matches the date prefix, fall back to the dropzone files found.
    if not matched_dropzone and all_dropzone_files:
        # Keep files whose name contains yyyymmdd.
        matched_dropzone = [f for f in all_dropzone_files if yyyymmdd in f]

    # Check the existing partition in the store for incremental compaction.
    existing_partition_rel = f"{output_base}/year={year}/month={month}/part-{yyyymmdd}.parquet"
    existing_files: list[str] = []
    if storage.exists(existing_partition_rel):
        existing_files.append(existing_partition_rel)

    all_input_files = existing_files + matched_dropzone

    if not all_input_files:
        elapsed = (time.perf_counter() - t_start) * 1000
        return ConsolidationResult(
            date_str=date_str,
            total_scanned=0,
            unique_articles=0,
            partition_file="",
            manifest_file="",
            sha256="",
            elapsed_ms=elapsed,
            partitions=[],
        )

    # Open an in-process DuckDB connection.
    con = duckdb.connect()
    try:
        con.execute("PRAGMA threads = 4;")
        con.execute("PRAGMA memory_limit = '2GB';")

        # Use local paths when possible; otherwise read the bytes into a PyArrow Table.
        local_paths: list[str] = []
        for rel_f in all_input_files:
            loc = storage.get_local_path(rel_f)
            if loc is not None and loc.is_file():
                local_paths.append(loc.as_posix())

        if len(local_paths) == len(all_input_files):
            # Fast path: read the files on disk directly through the DuckDB vectorized engine.
            source_expr = "read_parquet(?)"
            query_params = [local_paths]
        else:
            # Fallback: read the data through the adapter read_bytes and load it into a PyArrow Table.
            arrow_tables: list[pa.Table] = []
            for rel_f in all_input_files:
                b = storage.read_bytes(rel_f)
                arrow_tables.append(pq.read_table(io.BytesIO(b)))
            combined_arrow = pa.concat_tables(arrow_tables)
            con.register("raw_lakehouse_input", combined_arrow)
            source_expr = "raw_lakehouse_input"
            query_params = []

        # Run the deduplication query with a priority order.
        count_sql = f"SELECT count(*) FROM {source_expr}"
        total_scanned = con.execute(count_sql, query_params).fetchone()[0]

        dedup_sql = f"""
            SELECT 
                article_id,
                url,
                title,
                source_domain,
                published_at,
                updated_at,
                dev_id,
                batch_id,
                summary,
                key_points,
                implication,
                sentiment,
                time_sensitivity,
                citations,
                entities,
                symbols,
                categories,
                intent_llm,
                intent_code,
                intent_source,
                gold_status,
                raw_sha256
            FROM {source_expr}
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY article_id 
                ORDER BY updated_at DESC, batch_id DESC
            ) = 1
            ORDER BY published_at DESC, article_id ASC;
        """
        result_arrow = con.execute(dedup_sql, query_params).to_arrow_table()
        unique_articles = len(result_arrow)

        # Convert the result to ZSTD-compressed Parquet.
        buf = io.BytesIO()
        pq.write_table(result_arrow, buf, compression="ZSTD")
        parquet_bytes = buf.getvalue()


        # Write the partition file atomically through the storage adapter.
        target_partition_rel = f"{output_base}/year={year}/month={month}/part-{yyyymmdd}.parquet"
        saved_partition_path = storage.write_atomic(target_partition_rel, parquet_bytes)
        sha256_hash = hashlib.sha256(parquet_bytes).hexdigest()

        # Create the manifest entry and update latest.json.
        part_entry = PartitionManifestEntry(
            partition_path=saved_partition_path,
            row_count=unique_articles,
            size_bytes=len(parquet_bytes),
            sha256=sha256_hash,
            year=year,
            month=month,
            date=yyyymmdd,
        )

        saved_manifest, _ = write_manifests(
            date_str=date_str,
            partitions=[part_entry],
            storage=storage,
            engine_name=f"DuckDB {duckdb.__version__}",
        )

        # Purge the fragment files in the dropzone after a successful merge.
        if auto_purge and matched_dropzone:
            for dz_file in matched_dropzone:
                try:
                    storage.delete(dz_file)
                except Exception:
                    pass

        elapsed_ms = (time.perf_counter() - t_start) * 1000

        return ConsolidationResult(
            date_str=date_str,
            total_scanned=total_scanned,
            unique_articles=unique_articles,
            partition_file=saved_partition_path,
            manifest_file=saved_manifest,
            sha256=sha256_hash,
            elapsed_ms=elapsed_ms,
            partitions=[part_entry],
        )
    finally:
        con.close()
