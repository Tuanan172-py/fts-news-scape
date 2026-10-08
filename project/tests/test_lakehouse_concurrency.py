"""Kiểm thử mô phỏng đa Dev đẩy dữ liệu đồng thời vào vùng nạp Dropzone phi khóa."""

from __future__ import annotations

import concurrent.futures
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pyarrow.parquet as pq
import pytest

from src.lakehouse.ingest import publish_batch
from src.lakehouse.storage import BaseStorageAdapter, LocalOneDriveStorageAdapter


def _generate_article_batch(
    start_id: int,
    count: int,
    dev_id: str,
    batch_id: str,
    timestamp: str,
) -> list[dict]:
    """Sinh danh sách bản ghi bài viết phục vụ kiểm thử.

    Args:
        start_id: Chỉ số bắt đầu định danh bài viết.
        count: Số lượng bài viết cần sinh.
        dev_id: Mã định danh Dev xuất bản.
        batch_id: Mã định danh lô bài viết.
        timestamp: Mốc thời gian cập nhật của bản ghi.

    Returns:
        Danh sách các từ điển dữ liệu bài viết chuẩn hóa.
    """
    records = []
    for i in range(start_id, start_id + count):
        art_id = f"art_{i:04d}"
        records.append(
            {
                "article_id": art_id,
                "url": f"https://cafef.vn/{art_id}.chn",
                "title": f"Báo cáo tài chính doanh nghiệp {art_id}",
                "source_domain": "cafef.vn",
                "published_at": timestamp,
                "updated_at": timestamp,
                "dev_id": dev_id,
                "batch_id": batch_id,
                "summary": f"Tóm tắt nội dung thông tin tài chính cho {art_id}.",
                "key_points": [f"Luận điểm 1 của {art_id}", f"Luận điểm 2 của {art_id}"],
                "implication": f"Tác động thị trường tích cực đến dòng tiền doanh nghiệp {art_id}.",
                "sentiment": "pos" if i % 2 == 0 else "neu",
                "time_sensitivity": "today",
                "citations": [f"Trích dẫn nguyên văn kiểm chứng từ nguồn tin cho {art_id}"],
                "entities": ["HPG", "THEP"],
                "symbols": "HPG",
                "categories": "TAI_CHINH",
                "intent_llm": "HPG",
                "intent_code": "HPG",
                "intent_source": "BOTH",
                "gold_status": "GOLD",
                "raw_sha256": f"hash_{art_id}",
            }
        )
    return records


def _assert_zero_conflict_and_partial_files(root_path: Path) -> None:
    """Xác nhận không tồn tại tệp xung đột đồng bộ hoặc tệp tạm còn sót lại.

    Args:
        root_path: Thư mục gốc cần quét đệ quy.
    """
    for item in root_path.rglob("*"):
        if item.is_file():
            name = item.name
            assert "-DESKTOP-" not in name, f"Phát hiện tệp xung đột OneDrive: {item}"
            assert "-FPA-" not in name, f"Phát hiện tệp xung đột máy trạm: {item}"
            assert not name.endswith(".partial"), f"Phát hiện tệp tạm chưa hoàn tất: {item}"
            assert not name.endswith(".tmp"), f"Phát hiện tệp tmp còn sót: {item}"


def test_three_devs_concurrent_dropzone_publishing():
    """Mô phỏng 3 Devs đẩy đồng thời 3 lô dữ liệu trùng lặp một phần vào Dropzone."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
        date_str = "2026-10-08"

        # Dev 1 (alpha): 500 bài viết (art_0001 -> art_0500)
        batch_alpha = _generate_article_batch(
            start_id=1,
            count=500,
            dev_id="dev_alpha",
            batch_id="b01",
            timestamp="2026-10-08T08:00:00Z",
        )
        # Dev 2 (beta): 500 bài viết (art_0251 -> art_0750, trùng 250 bài với alpha)
        batch_beta = _generate_article_batch(
            start_id=251,
            count=500,
            dev_id="dev_beta",
            batch_id="b02",
            timestamp="2026-10-08T08:10:00Z",
        )
        # Dev 3 (gamma): 500 bài viết (art_0500 -> art_0999, trùng bài với cả alpha và beta)
        batch_gamma = _generate_article_batch(
            start_id=500,
            count=500,
            dev_id="dev_gamma",
            batch_id="b03",
            timestamp="2026-10-08T08:20:00Z",
        )

        tasks = [
            (batch_alpha, date_str, "dev_alpha", "b01"),
            (batch_beta, date_str, "dev_beta", "b02"),
            (batch_gamma, date_str, "dev_gamma", "b03"),
        ]

        def _worker_publish(args):
            records, dt, dev, batch = args
            worker_storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
            return publish_batch(
                records=records,
                date_str=dt,
                dev_id=dev,
                batch_id=batch,
                storage=worker_storage,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            published_paths = list(executor.map(_worker_publish, tasks))

        assert len(published_paths) == 3
        for rel_p in published_paths:
            assert storage.exists(rel_p)
            full_p = tmp_path / rel_p
            table = pq.read_table(full_p)
            assert table.num_rows == 500

        # Kiểm tra không có tệp xung đột hay tệp tạm dở dang
        _assert_zero_conflict_and_partial_files(tmp_path)

        # Kiểm tra cấu trúc phân mục ngày tháng chuẩn POSIX
        dropzone_files = storage.list_files("dropzone/2026/10/08/*.parquet")
        assert len(dropzone_files) == 3
        assert any("dev_alpha" in f for f in dropzone_files)
        assert any("dev_beta" in f for f in dropzone_files)
        assert any("dev_gamma" in f for f in dropzone_files)


def test_concurrent_multiple_batches_per_worker():
    """Mô phỏng nhiều Devs đẩy liên tiếp nhiều đợt dữ liệu đồng thời."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
        date_str = "2026-10-08"

        payloads = []
        for worker_idx in range(4):
            dev_id = f"w{worker_idx}"
            for batch_idx in range(3):
                batch_id = f"b{batch_idx:02d}"
                records = _generate_article_batch(
                    start_id=(worker_idx * 100) + (batch_idx * 20),
                    count=30,
                    dev_id=dev_id,
                    batch_id=batch_id,
                    timestamp="2026-10-08T09:00:00Z",
                )
                payloads.append((records, date_str, dev_id, batch_id))

        def _run_publish(item):
            recs, dt, dev, b_id = item
            worker_storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
            return publish_batch(recs, dt, dev, b_id, worker_storage)

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            saved_paths = list(executor.map(_run_publish, payloads))

        assert len(saved_paths) == 12
        dropzone_files = storage.list_files("dropzone/2026/10/08/*.parquet")
        assert len(dropzone_files) == 12
        _assert_zero_conflict_and_partial_files(tmp_path)


def test_publish_batch_input_validation(tmp_path: Path):
    """Kiểm tra phản ứng bắt lỗi khi đầu vào xuất bản không hợp lệ.

    Args:
        tmp_path: Thư mục tạm độc lập do pytest cung cấp.
    """
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)

    # Danh sách bản ghi rỗng
    with pytest.raises(ValueError, match="rỗng"):
        publish_batch([], "2026-10-08", "dev1", "b01", storage)

    # Thiếu dev_id
    sample_records = _generate_article_batch(1, 5, "dev1", "b01", "2026-10-08T08:00:00Z")
    with pytest.raises(ValueError, match="dev_id"):
        publish_batch(sample_records, "2026-10-08", "", "b01", storage)

    # Thiếu batch_id
    with pytest.raises(ValueError, match="batch_id"):
        publish_batch(sample_records, "2026-10-08", "dev1", "", storage)

    # Định dạng ngày không hợp lệ
    with pytest.raises(ValueError, match="ngày"):
        publish_batch(sample_records, "invalid-date", "dev1", "b01", storage)


def test_atomic_write_fallback_on_locked_file(tmp_path: Path):
    """Kiểm tra cơ chế dự phòng an toàn khi tệp đích bị khóa độc quyền trên Windows.

    Args:
        tmp_path: Thư mục tạm độc lập do pytest cung cấp.
    """
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
    target_rel = "dropzone/2026/10/08/part-20261008-dev_test-b01.parquet"
    target_full = tmp_path / target_rel
    target_full.parent.mkdir(parents=True, exist_ok=True)
    target_full.write_bytes(b"initial data")

    original_replace = os.replace

    def mock_replace(src, dst):
        if Path(dst) == target_full:
            raise PermissionError("[WinError 32] The process cannot access the file")
        return original_replace(src, dst)

    with patch("os.replace", side_effect=mock_replace):
        saved_rel = storage.write_atomic(target_rel, b"new updated data")

    assert saved_rel != target_rel
    assert storage.exists(saved_rel)
    assert "_test-b01_" in saved_rel
    _assert_zero_conflict_and_partial_files(tmp_path)


def test_storage_adapter_idempotency_byte_check(tmp_path: Path):
    """Kiểm định tính lũy đống không ghi thừa khi dữ liệu nhị phân giống hệt.

    Args:
        tmp_path: Thư mục tạm độc lập do pytest cung cấp.
    """
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
    rel_path = "test_dir/sample.bin"
    payload = b"constant content 12345"

    path1 = storage.write_atomic(rel_path, payload)
    mtime1 = (tmp_path / rel_path).stat().st_mtime_ns

    # Ghi lại cùng nội dung
    path2 = storage.write_atomic(rel_path, payload)
    mtime2 = (tmp_path / rel_path).stat().st_mtime_ns

    assert path1 == path2
    assert mtime1 == mtime2
