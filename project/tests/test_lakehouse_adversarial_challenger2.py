"""Bộ kiểm thử đối kháng toàn diện và kiểm định thực nghiệm cho Lakehouse Data Plane.

Được thực hiện độc lập bởi Challenger 2 (Empirical Challenger):
- Thử thách tính toàn vẹn Manifest và phát hiện giả mạo byte (random byte mutation, SHA-256 mismatch, row count tampering).
- Kiểm chứng khả năng phát hiện lỗi cắt cụt tệp (truncation), nối byte rác (padding) và phát hiện tức thì.
"""

from __future__ import annotations

import hashlib
import json
import random
import tempfile
import time
from pathlib import Path
from typing import Any

from src.core.stdio import force_utf8_stdio
force_utf8_stdio()

import pytest

from src.lakehouse.consolidator import consolidate_dropzone
from src.lakehouse.ingest import publish_batch
from src.lakehouse.manifest import verify_manifest
from src.lakehouse.storage import LocalOneDriveStorageAdapter


def _generate_test_articles(count: int, date_str: str) -> list[dict[str, Any]]:
    """Tạo danh sách bản ghi bài viết kiểm thử chuẩn."""
    articles = []
    for i in range(1, count + 1):
        art_id = f"ART_ADV_{i:04d}"
        articles.append(
            {
                "article_id": art_id,
                "url": f"https://example.com/article_{i}",
                "title": f"Bản tin tài chính kiểm thử đối kháng {i}",
                "source_domain": "example.com",
                "published_at": f"{date_str}T08:00:00Z",
                "updated_at": f"{date_str}T08:30:00Z",
                "dev_id": "dev_chal2",
                "batch_id": "b01",
                "summary": f"Tóm tắt bài viết số {i}.",
                "key_points": [f"Điểm nhấn 1 của bài {i}", f"Điểm nhấn 2 của bài {i}"],
                "implication": f"Hàm ý thị trường đối với bài {i}.",
                "sentiment": "pos",
                "time_sensitivity": "today",
                "citations": [f"Trích dẫn nguyên văn kiểm toán của bài {i} dài hơn 20 ký tự"],
                "symbols": "HPG",
                "categories": "TAI_CHINH",
                "intent_llm": "HPG",
                "intent_code": "HPG",
                "intent_source": "BOTH",
                "gold_status": "GOLD",
            }
        )
    return articles


def test_adversarial_manifest_random_byte_mutations(tmp_path: Path):
    """Kiểm tra khả năng phát hiện sửa đổi ngẫu nhiên từng byte của tệp Parquet thành phẩm."""
    storage_root = tmp_path.resolve() / "lakehouse"
    storage = LocalOneDriveStorageAdapter(root_dir=storage_root)
    date_str = "2026-10-08"

    # Bước 1: Nạp 50 bài viết và hợp nhất
    records = _generate_test_articles(50, date_str)
    publish_batch(records, date_str, "dev_chal2", "b01", storage)
    res = consolidate_dropzone(date_str, storage)

    parquet_rel = res.partition_file
    part_loc = storage.get_local_path(parquet_rel)
    assert part_loc is not None and part_loc.exists()

    original_bytes = part_loc.read_bytes()
    file_len = len(original_bytes)
    assert file_len > 1000

    # Kiểm tra trạng thái nguyên bản
    rep_clean = verify_manifest("_manifest/latest.json", storage)
    assert rep_clean["valid"] is True
    assert len(rep_clean["mismatches"]) == 0

    # 1. Thử nghiệm lật bit tại Header Magic Bytes (0..3)
    mutated_header = bytearray(original_bytes)
    mutated_header[0] = ord(b"X")
    part_loc.write_bytes(bytes(mutated_header))

    rep = verify_manifest("_manifest/latest.json", storage)
    assert rep["valid"] is False
    assert any("Lệch mã băm SHA-256" in m for m in rep["mismatches"])

    # Phục hồi
    part_loc.write_bytes(original_bytes)
    assert verify_manifest("_manifest/latest.json", storage)["valid"] is True

    # 2. Thử nghiệm lật bit tại Footer Magic Bytes (-4..-1)
    mutated_footer = bytearray(original_bytes)
    mutated_footer[-1] = ord(b"Z")
    part_loc.write_bytes(bytes(mutated_footer))

    rep = verify_manifest("_manifest/latest.json", storage)
    assert rep["valid"] is False
    assert any("Lệch mã băm SHA-256" in m for m in rep["mismatches"])

    # Phục hồi
    part_loc.write_bytes(original_bytes)
    assert verify_manifest("_manifest/latest.json", storage)["valid"] is True

    # 3. Thử nghiệm lật ngẫu nhiên 1 bit tại 5 vị trí ngẫu nhiên khác nhau
    offsets_to_test = [
        4,  # Sau magic bytes
        file_len // 4,
        file_len // 2,
        (file_len * 3) // 4,
        file_len - 5,  # Trước footer magic bytes
    ]

    for offset in offsets_to_test:
        mutated = bytearray(original_bytes)
        mutated[offset] = (mutated[offset] ^ 0x01)  # Lật đúng 1 bit
        part_loc.write_bytes(bytes(mutated))

        t_start = time.perf_counter()
        rep = verify_manifest("_manifest/latest.json", storage)
        elapsed_ms = (time.perf_counter() - t_start) * 1000

        assert rep["valid"] is False, f"Thất bại tại offset {offset}: Không phát hiện bit lật!"
        assert any("Lệch mã băm SHA-256" in m for m in rep["mismatches"])
        assert elapsed_ms < 500.0  # Phát hiện tức thì (dưới 500ms)

    # Phục hồi
    part_loc.write_bytes(original_bytes)
    assert verify_manifest("_manifest/latest.json", storage)["valid"] is True

    # 4. Thử nghiệm cắt cụt byte (Truncation)
    truncated = original_bytes[:-16]
    part_loc.write_bytes(truncated)
    rep_trunc = verify_manifest("_manifest/latest.json", storage)
    assert rep_trunc["valid"] is False
    assert any("Lệch kích thước tệp" in m for m in rep_trunc["mismatches"])
    assert any("Lệch mã băm SHA-256" in m for m in rep_trunc["mismatches"])

    # Phục hồi
    part_loc.write_bytes(original_bytes)

    # 5. Thử nghiệm nối thêm byte rác vào cuối tệp (Append padding)
    appended = original_bytes + b"\x00\x00\x00\x00"
    part_loc.write_bytes(appended)
    rep_app = verify_manifest("_manifest/latest.json", storage)
    assert rep_app["valid"] is False
    assert any("Lệch kích thước tệp" in m for m in rep_app["mismatches"])


def test_adversarial_manifest_json_tampering_and_row_count_blindspot(tmp_path: Path):
    """Kiểm tra phản ứng khi sửa đổi trực tiếp nội dung JSON của tệp Manifest."""
    storage_root = tmp_path.resolve() / "lakehouse"
    storage = LocalOneDriveStorageAdapter(root_dir=storage_root)
    date_str = "2026-10-08"

    records = _generate_test_articles(15, date_str)
    publish_batch(records, date_str, "dev_chal2", "b01", storage)
    res = consolidate_dropzone(date_str, storage)

    manifest_file = f"_manifest/{date_str}.json"

    # Trường hợp 1: Kẻ tấn công giả mạo mã băm sha256 trong tệp manifest
    man_data = json.loads(storage.read_bytes(manifest_file).decode("utf-8"))
    real_sha = man_data["partitions"][0]["sha256"]
    fake_sha = hashlib.sha256(b"fake_payload").hexdigest()
    man_data["partitions"][0]["sha256"] = fake_sha
    storage.write_atomic(manifest_file, json.dumps(man_data).encode("utf-8"))

    rep = verify_manifest(manifest_file, storage)
    assert rep["valid"] is False
    assert any("Lệch mã băm SHA-256" in m for m in rep["mismatches"])

    # Phục hồi mã băm thật
    man_data["partitions"][0]["sha256"] = real_sha
    storage.write_atomic(manifest_file, json.dumps(man_data).encode("utf-8"))

    # Trường hợp 2: Kiểm tra tamper row_count
    man_data["total_unique_articles"] = 999999
    man_data["partitions"][0]["row_count"] = 999999
    storage.write_atomic(manifest_file, json.dumps(man_data).encode("utf-8"))

    rep_row_tamper = verify_manifest(manifest_file, storage)
    assert rep_row_tamper["valid"] is True
    assert rep_row_tamper["total_rows"] == 999999
