"""Kiểm thử khử trùng lặp dữ liệu bài viết 100% bằng DuckDB theo article_id và updated_at mới nhất."""

from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest

from src.lakehouse.consolidator import ConsolidationResult, consolidate_dropzone
from src.lakehouse.ingest import publish_batch
from src.lakehouse.storage import LocalOneDriveStorageAdapter


def _build_records(
    start: int,
    end: int,
    dev_id: str,
    batch_id: str,
    updated_at: str,
    title_suffix: str = "",
) -> list[dict]:
    """Sinh danh sách bản ghi bài viết có dải chỉ số xác định.

    Args:
        start: Chỉ số ID bắt đầu (bao gồm).
        end: Chỉ số ID kết thúc (bao gồm).
        dev_id: Mã định danh Dev xuất bản.
        batch_id: Mã định danh lô bài viết.
        updated_at: Mốc thời gian cập nhật.
        title_suffix: Hậu tố tiêu đề để nhận diện nguồn cập nhật.

    Returns:
        Danh sách các từ điển dữ liệu bài viết.
    """
    records = []
    for i in range(start, end + 1):
        art_id = f"art_{i:04d}"
        suffix = title_suffix or dev_id
        records.append(
            {
                "article_id": art_id,
                "url": f"https://cafef.vn/{art_id}.chn",
                "title": f"Báo cáo tin tức {art_id} [{suffix}]",
                "source_domain": "cafef.vn",
                "published_at": "2026-10-08T07:00:00Z",
                "updated_at": updated_at,
                "dev_id": dev_id,
                "batch_id": batch_id,
                "summary": f"Tóm tắt bài viết {art_id} bởi {dev_id}.",
                "key_points": [f"Điểm chính 1 của {art_id}", f"Điểm chính 2 của {art_id}"],
                "implication": f"Hàm ý doanh nghiệp {art_id}.",
                "sentiment": "pos",
                "time_sensitivity": "today",
                "citations": [f"Dẫn chứng xác thực {art_id}"],
                "entities": ["TICKER:HPG"],
                "symbols": "HPG",
                "categories": "TAI_CHINH",
                "intent_llm": "HPG",
                "intent_code": "HPG",
                "intent_source": "BOTH",
                "gold_status": "GOLD",
                "raw_sha256": f"sha_{art_id}",
            }
        )
    return records


def test_duckdb_dedup_full_coverage(tmp_path: Path):
    """Kiểm tra khử trùng lặp 100% khi gộp 3 lô dữ liệu từ 3 Devs với các dải chồng lấn.

    Args:
        tmp_path: Thư mục tạm độc lập do pytest cung cấp.
    """
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
    date_str = "2026-10-08"

    # Lô 1 (dev_alpha): 500 bài viết (art_0001 -> art_0500), thời điểm T1
    t1 = "2026-10-08T08:00:00Z"
    batch_alpha = _build_records(1, 500, "dev_alpha", "b01", t1)
    publish_batch(batch_alpha, date_str, "dev_alpha", "b01", storage)

    # Lô 2 (dev_beta): 500 bài viết (art_0251 -> art_0750), thời điểm T2 (T2 > T1)
    t2 = "2026-10-08T08:15:00Z"
    batch_beta = _build_records(251, 750, "dev_beta", "b02", t2)
    publish_batch(batch_beta, date_str, "dev_beta", "b02", storage)

    # Lô 3 (dev_gamma): 500 bài viết (art_0500 -> art_0999), thời điểm T3 (T3 > T2)
    t3 = "2026-10-08T08:30:00Z"
    batch_gamma = _build_records(500, 999, "dev_gamma", "b03", t3)
    publish_batch(batch_gamma, date_str, "dev_gamma", "b03", storage)

    # Thực hiện hợp nhất và khử trùng lặp
    result = consolidate_dropzone(date_str=date_str, storage=storage)

    # Tổng số bản ghi quét được: 500 + 500 + 500 = 1.500 dòng
    assert result.total_scanned == 1500
    # Số lượng bài viết duy nhất: từ art_0001 đến art_0999 = 999 bài
    assert result.unique_articles == 999
    assert storage.exists(result.partition_file)

    # Đọc trực tiếp tệp Parquet thành phẩm bằng DuckDB
    con = duckdb.connect()
    try:
        part_local = storage.get_local_path(result.partition_file)
        assert part_local is not None

        # 1. Xác minh không còn bất kỳ article_id nào bị lặp
        dup_count = con.execute(
            f"SELECT count(*) FROM (SELECT article_id, count(*) FROM read_parquet('{part_local.as_posix()}') GROUP BY article_id HAVING count(*) > 1)"
        ).fetchone()[0]
        assert dup_count == 0

        # 2. Xác minh tổng số dòng khớp chính xác 999
        total_rows = con.execute(
            f"SELECT count(*) FROM read_parquet('{part_local.as_posix()}')"
        ).fetchone()[0]
        assert total_rows == 999

        # 3. Xác minh độ ưu tiên updated_at mới nhất cho bài giao thoa 2 Devs (art_0251)
        # Có ở alpha (T1) và beta (T2) -> kết quả phải giữ bản của beta (T2)
        row_251 = con.execute(
            f"SELECT dev_id, updated_at, title FROM read_parquet('{part_local.as_posix()}') WHERE article_id = 'art_0251'"
        ).fetchone()
        assert row_251[0] == "dev_beta"
        assert row_251[1] == t2
        assert "[dev_beta]" in row_251[2]

        # 4. Xác minh độ ưu tiên cho bài giao thoa cả 3 Devs (art_0500)
        # Có ở alpha (T1), beta (T2) và gamma (T3) -> kết quả phải giữ bản của gamma (T3)
        row_500 = con.execute(
            f"SELECT dev_id, updated_at, title FROM read_parquet('{part_local.as_posix()}') WHERE article_id = 'art_0500'"
        ).fetchone()
        assert row_500[0] == "dev_gamma"
        assert row_500[1] == t3
        assert "[dev_gamma]" in row_500[2]

        # 5. Xác minh bài không giao thoa vẫn giữ nguyên đúng thông tin
        row_001 = con.execute(
            f"SELECT dev_id, updated_at FROM read_parquet('{part_local.as_posix()}') WHERE article_id = 'art_0001'"
        ).fetchone()
        assert row_001[0] == "dev_alpha"
        assert row_001[1] == t1

        row_999 = con.execute(
            f"SELECT dev_id, updated_at FROM read_parquet('{part_local.as_posix()}') WHERE article_id = 'art_0999'"
        ).fetchone()
        assert row_999[0] == "dev_gamma"
        assert row_999[1] == t3
    finally:
        con.close()


def test_incremental_compaction_with_existing_partition(tmp_path: Path):
    """Kiểm tra khả năng nạp gia tăng và gộp với phân vùng đã tồn tại trước đó.

    Args:
        tmp_path: Thư mục tạm độc lập do pytest cung cấp.
    """
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
    date_str = "2026-10-08"

    # Đợt 1: Nạp 100 bài đầu tiên (art_0001 -> art_0100)
    batch_initial = _build_records(1, 100, "dev_init", "b01", "2026-10-08T06:00:00Z")
    publish_batch(batch_initial, date_str, "dev_init", "b01", storage)

    res1 = consolidate_dropzone(date_str=date_str, storage=storage)
    assert res1.unique_articles == 100

    # Đợt 2: Thêm lô mới cập nhật bài art_0050 và thêm bài mới art_0101 -> art_0150
    t_new = "2026-10-08T10:00:00Z"
    batch_update = _build_records(50, 150, "dev_update", "b02", t_new, title_suffix="UPDATED")
    publish_batch(batch_update, date_str, "dev_update", "b02", storage)

    res2 = consolidate_dropzone(date_str=date_str, storage=storage)
    # Tổng bản ghi duy nhất mới: 150 bài
    assert res2.unique_articles == 150

    con = duckdb.connect()
    try:
        part_local = storage.get_local_path(res2.partition_file)
        assert part_local is not None
        row_50 = con.execute(
            f"SELECT dev_id, updated_at, title FROM read_parquet('{part_local.as_posix()}') WHERE article_id = 'art_0050'"
        ).fetchone()
        assert row_50[0] == "dev_update"
        assert row_50[1] == t_new
        assert "UPDATED" in row_50[2]

        row_150 = con.execute(
            f"SELECT dev_id, updated_at, title FROM read_parquet('{part_local.as_posix()}') WHERE article_id = 'art_0150'"
        ).fetchone()
        assert row_150[0] == "dev_update"
    finally:
        con.close()


def test_consolidate_empty_dropzone(tmp_path: Path):
    """Kiểm tra xử lý khi vùng nạp dropzone rỗng.

    Args:
        tmp_path: Thư mục tạm độc lập do pytest cung cấp.
    """
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
    res = consolidate_dropzone(date_str="2026-10-08", storage=storage)
    assert res.total_scanned == 0
    assert res.unique_articles == 0
    assert res.partition_file == ""


def test_tie_breaking_same_updated_at(tmp_path: Path):
    """Kiểm tra quy tắc phân giải hòa khi mốc updated_at bằng nhau dựa trên batch_id giảm dần.

    Args:
        tmp_path: Thư mục tạm độc lập do pytest cung cấp.
    """
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
    date_str = "2026-10-08"
    same_time = "2026-10-08T12:00:00Z"

    # Cùng mốc thời gian nhưng batch_id khác nhau (b01 vs b09)
    batch_early = _build_records(1, 10, "dev_a", "b01", same_time, title_suffix="EARLY")
    batch_late = _build_records(1, 10, "dev_a", "b09", same_time, title_suffix="LATE")

    publish_batch(batch_early, date_str, "dev_a", "b01", storage)
    publish_batch(batch_late, date_str, "dev_a", "b09", storage)

    res = consolidate_dropzone(date_str=date_str, storage=storage)
    assert res.unique_articles == 10

    con = duckdb.connect()
    try:
        part_local = storage.get_local_path(res.partition_file)
        assert part_local is not None
        rows = con.execute(
            f"SELECT batch_id, title FROM read_parquet('{part_local.as_posix()}')"
        ).fetchall()
        for b_id, title in rows:
            assert b_id == "b09"
            assert "LATE" in title
    finally:
        con.close()
