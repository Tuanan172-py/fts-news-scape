"""
Tests for Staging, Safe Atomic Write, Non-blocking SQLite connections, and DB Snapshot.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.models import Article
from src.core.staging import (
    clean_stale_staging,
    ensure_staging_dir,
    safe_atomic_write,
    safe_json_dump,
)
from src.db.snapshot import create_db_snapshot
from src.db.store import ArticleStore
from src.export.csv_export import write_csv


def test_safe_atomic_write_basic(tmp_path: Path):
    target = tmp_path / "test.csv"
    content = "col1,col2\nval1,val2\n"

    final_path, is_fallback = safe_atomic_write(target, content)
    assert final_path == target
    assert not is_fallback
    assert target.exists()
    assert target.read_text(encoding="utf-8") == content


def test_safe_atomic_write_locked_fallback(tmp_path: Path):
    target = tmp_path / "locked_file.csv"
    target.write_text("initial content", encoding="utf-8")

    # Giả lập PermissionError khi os.replace trên Windows (khi Excel đang mở file)
    orig_replace = os.replace

    def mock_replace(src, dst):
        if Path(dst) == target:
            raise PermissionError("[WinError 32] The process cannot access the file because it is being used by another process")
        return orig_replace(src, dst)

    with patch("os.replace", side_effect=mock_replace):
        final_path, is_fallback = safe_atomic_write(
            target,
            "new content",
            fallback_on_lock=True,
        )

    assert is_fallback is True
    assert final_path != target
    assert final_path.exists()
    assert final_path.name.startswith("locked_file_")
    assert final_path.suffix == ".csv"
    assert final_path.read_text(encoding="utf-8") == "new content"
    # File gốc ban đầu vẫn giữ nguyên
    assert target.read_text(encoding="utf-8") == "initial content"


def test_safe_json_dump(tmp_path: Path):
    target = tmp_path / "packet.json"
    data = {"article_id": "test-123", "title": "Tin tức thị trường"}

    final_path, is_fallback = safe_json_dump(data, target)
    assert final_path == target
    assert not is_fallback
    assert target.exists()
    import json
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded["article_id"] == "test-123"


def test_clean_stale_staging(tmp_path: Path):
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()

    fresh_file = staging_dir / "fresh.tmp"
    fresh_file.write_text("fresh")

    stale_file = staging_dir / "stale.tmp"
    stale_file.write_text("stale")
    # Đặt thời gian mtime cũ hơn 100s
    past_time = time.time() - 200
    os.utime(stale_file, (past_time, past_time))

    cleaned = clean_stale_staging(staging_dir, max_age_seconds=100)
    assert cleaned == 1
    assert not stale_file.exists()
    assert fresh_file.exists()


def test_store_readonly_and_concurrent_access(tmp_path: Path):
    db_file = str(tmp_path / "test_monocle.db")
    store = ArticleStore(db_path=db_file)

    art = Article(
        url="https://cafef.vn/bai-1.chn",
        title="Tiêu đề thử nghiệm",
        summary="Tóm tắt",
        content_text="Nội dung bài viết",
        source_domain="cafef",
        published_at="2026-08-24T12:00:00+07:00",
        fetched_at="2026-08-24T12:05:00+07:00",
    )
    assert store.insert(art) is True
    assert store.count() == 1

    # Kiểm tra connection readonly
    ro_conn = store._connect_ro()
    try:
        row = ro_conn.execute("SELECT count(*) FROM articles").fetchone()
        assert row[0] == 1
    finally:
        ro_conn.close()

    # Kiểm tra get_by_hash
    retrieved = store.get_by_hash(art.url_title_hash)
    assert retrieved is not None
    assert retrieved.title == "Tiêu đề thử nghiệm"


def test_db_snapshot_creation(tmp_path: Path):
    src_db = tmp_path / "source.db"
    store = ArticleStore(db_path=str(src_db))

    for i in range(5):
        store.insert(Article(
            url=f"https://cafef.vn/bai-{i}.chn",
            title=f"Tiêu đề {i}",
            summary="Tóm tắt",
            content_text="Nội dung",
            source_domain="cafef",
            published_at="2026-08-24T12:00:00+07:00",
            fetched_at="2026-08-24T12:05:00+07:00",
        ))

    dst_db = tmp_path / "snapshot_review.db"
    snapshot_path = create_db_snapshot(src_db_path=src_db, dst_db_path=dst_db)

    assert snapshot_path == dst_db
    assert dst_db.exists()

    # Đọc độc lập từ snapshot db
    con = sqlite3.connect(dst_db)
    try:
        count = con.execute("SELECT count(*) FROM articles").fetchone()[0]
        assert count == 5
    finally:
        con.close()
