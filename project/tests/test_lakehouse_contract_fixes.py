"""TDD tests verifying data contract bug fixes (GLB-DEC-076 §4).

1. Unprocessed articles must not default to sentiment='neutral' and gold_status='GOLD'.
2. Rows with an empty article_id must not collapse into a single row.
3. updated_at comparison must handle mixed-format timestamps correctly (newer time wins).
4. Reused batch_id must not overwrite an existing fragment file.
"""

from __future__ import annotations

import io
from pathlib import Path
import duckdb
import pyarrow.parquet as pq
import pytest

from src.lakehouse.consolidator import consolidate_dropzone
from src.lakehouse.ingest import (
    LAKEHOUSE_ARTICLE_SCHEMA,
    publish_batch,
    sanitize_article_record,
)
from src.lakehouse.storage import LocalOneDriveStorageAdapter


def test_sanitize_article_record_defaults():
    """Unprocessed articles must have sentiment='' and gold_status='RAW', not neutral/GOLD."""
    raw_record = {
        "article_id": "art_test_01",
        "url": "https://example.com/test1",
        "title": "Unprocessed article",
    }
    sanitized = sanitize_article_record(
        raw_record,
        dev_id="dev_test",
        batch_id="b01",
        default_timestamp="2026-10-08T00:00:00Z",
    )

    assert sanitized["sentiment"] == "", "Unprocessed article sentiment must be empty, not 'neutral'"
    assert sanitized["gold_status"] == "RAW", "Unprocessed article gold_status must be 'RAW', not 'GOLD'"


def test_empty_article_id_does_not_collapse(tmp_path: Path):
    """Articles with empty or missing article_id must not collapse into 1 row."""
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
    date_str = "2026-10-08"

    # Three distinct articles, all with empty article_id
    records = [
        {
            "article_id": "",
            "url": "https://cafef.vn/post1.chn",
            "title": "First article with empty id",
            "source_domain": "cafef.vn",
            "published_at": "2026-10-08T07:00:00Z",
            "updated_at": "2026-10-08T07:00:00Z",
            "raw_sha256": "sha_post1",
        },
        {
            "article_id": "",
            "url": "https://cafef.vn/post2.chn",
            "title": "Second article with empty id",
            "source_domain": "cafef.vn",
            "published_at": "2026-10-08T07:05:00Z",
            "updated_at": "2026-10-08T07:05:00Z",
            "raw_sha256": "sha_post2",
        },
        {
            "article_id": "",
            "url": "https://cafef.vn/post3.chn",
            "title": "Third article with empty id",
            "source_domain": "cafef.vn",
            "published_at": "2026-10-08T07:10:00Z",
            "updated_at": "2026-10-08T07:10:00Z",
            "raw_sha256": "sha_post3",
        },
    ]

    publish_batch(records, date_str, "dev_test", "b01", storage)
    res = consolidate_dropzone(date_str=date_str, storage=storage)

    # Must preserve all 3 distinct articles, NOT collapse into 1 row
    assert res.unique_articles == 3


def test_mixed_format_timestamp_ordering(tmp_path: Path):
    """A newer updated_at must win even if string comparison would order it before."""
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
    date_str = "2026-10-08"

    # Early version: format with timezone Z
    early_rec = [
        {
            "article_id": "art_mixed_01",
            "url": "https://example.com/mixed",
            "title": "Early Version",
            "source_domain": "example.com",
            "published_at": "2026-10-08T07:00:00Z",
            "updated_at": "2026-10-08T08:00:00Z",
        }
    ]
    publish_batch(early_rec, date_str, "dev_a", "b01", storage)

    # Later version: format without Z (or space separated) at 09:30:00
    late_rec = [
        {
            "article_id": "art_mixed_01",
            "url": "https://example.com/mixed",
            "title": "Late Version",
            "source_domain": "example.com",
            "published_at": "2026-10-08T07:00:00Z",
            "updated_at": "2026-10-08 09:30:00",
        }
    ]
    publish_batch(late_rec, date_str, "dev_b", "b02", storage)

    res = consolidate_dropzone(date_str=date_str, storage=storage)
    assert res.unique_articles == 1

    con = duckdb.connect()
    try:
        part_local = storage.get_local_path(res.partition_file)
        row = con.execute(
            f"SELECT title, updated_at FROM read_parquet('{part_local.as_posix()}') WHERE article_id = 'art_mixed_01'"
        ).fetchone()
        assert row[0] == "Late Version", f"Expected Late Version to win, got {row[0]}"
    finally:
        con.close()


def test_naive_timestamp_order_does_not_depend_on_the_host_zone(tmp_path: Path, monkeypatch):
    """Naive stamps are UTC: a session that starts in ICT must still rank 09:30 naive after 08:00Z."""
    real_connect = duckdb.connect

    def connect_in_ict(*args, **kwargs):
        con = real_connect(*args, **kwargs)
        con.execute("SET TimeZone = 'Asia/Ho_Chi_Minh';")
        return con

    monkeypatch.setattr(duckdb, "connect", connect_in_ict)
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
    base = {"article_id": "art_tz_01", "url": "https://example.com/tz", "source_domain": "example.com",
            "published_at": "2026-10-08T07:00:00Z"}
    publish_batch([{**base, "title": "Early", "updated_at": "2026-10-08T08:00:00Z"}], "2026-10-08", "dev_a", "b01", storage)
    publish_batch([{**base, "title": "Late", "updated_at": "2026-10-08 09:30:00"}], "2026-10-08", "dev_b", "b02", storage)
    res = consolidate_dropzone(date_str="2026-10-08", storage=storage)
    monkeypatch.setattr(duckdb, "connect", real_connect)
    con = duckdb.connect()
    try:
        part = storage.get_local_path(res.partition_file).as_posix()
        assert con.execute(f"SELECT title FROM read_parquet('{part}')").fetchone()[0] == "Late"
    finally:
        con.close()


def test_reused_batch_id_does_not_overwrite_fragment(tmp_path: Path):
    """Calling publish_batch with the same dev_id and batch_id must not overwrite earlier fragment."""
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
    date_str = "2026-10-08"

    batch1 = [
        {
            "article_id": "art_reuse_01",
            "url": "https://example.com/1",
            "title": "Batch 1 article",
            "published_at": "2026-10-08T07:00:00Z",
            "updated_at": "2026-10-08T07:00:00Z",
        }
    ]
    path1 = publish_batch(batch1, date_str, "dev_same", "b01", storage)

    batch2 = [
        {
            "article_id": "art_reuse_02",
            "url": "https://example.com/2",
            "title": "Batch 2 article",
            "published_at": "2026-10-08T07:15:00Z",
            "updated_at": "2026-10-08T07:15:00Z",
        }
    ]
    path2 = publish_batch(batch2, date_str, "dev_same", "b01", storage)

    # Both fragment files must exist and be different
    assert path1 != path2, "Second batch with same batch_id must write to distinct fragment path"
    assert storage.exists(path1)
    assert storage.exists(path2)

    # Consolidator must find both articles
    res = consolidate_dropzone(date_str=date_str, storage=storage)
    assert res.unique_articles == 2
