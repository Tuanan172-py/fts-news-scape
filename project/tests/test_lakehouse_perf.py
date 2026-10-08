"""Kiểm thử chuẩn hiệu năng tổng hợp và khử trùng lặp 1.000 bài viết qua DuckDB."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.lakehouse.consolidator import consolidate_dropzone
from src.lakehouse.ingest import publish_batch
from src.lakehouse.storage import LocalOneDriveStorageAdapter


def _build_perf_dataset(
    storage: LocalOneDriveStorageAdapter,
    date_str: str,
) -> None:
    """Sinh tập dữ liệu hiệu năng gồm 1.300 bản ghi thô cho 1.000 bài viết duy nhất.

    Args:
        storage: Adapter giao tiếp hệ thống lưu trữ.
        date_str: Chuỗi ngày phân vùng.
    """
    tickers = ["HPG", "VCB", "VIC", "GAS", "VNM", "FPT", "SSI", "MSN", "MWG", "DGC"]
    industries = ["THEP", "NGAN_HANG", "BAT_DONG_SAN", "DAU_KHI", "THUC_PHAM", "CONG_NGHE"]

    # Đợt 1 (Dev Alpha): 500 bài viết (1 -> 500)
    batch1 = []
    for i in range(1, 501):
        art_id = f"art_{i:04d}"
        sym = tickers[i % len(tickers)]
        ind = industries[i % len(industries)]
        batch1.append(
            {
                "article_id": art_id,
                "url": f"https://cafef.vn/{art_id}.chn",
                "title": f"Báo cáo cập nhật tình hình hoạt động {sym} mã số {art_id}",
                "source_domain": "cafef.vn",
                "published_at": "2026-10-08T07:00:00Z",
                "updated_at": "2026-10-08T07:30:00Z",
                "dev_id": "dev_alpha",
                "batch_id": "b01",
                "summary": f"Tóm tắt kết quả kinh doanh quý cho cổ phiếu {sym}.",
                "key_points": [f"Điểm nhấn 1 về {sym}", f"Điểm nhấn 2 về {sym}"],
                "implication": f"Tác động tài chính tích cực tới doanh nghiệp {sym}.",
                "sentiment": "pos",
                "time_sensitivity": "today",
                "citations": [f"Trích dẫn nguyên văn kiểm toán của {sym}"],
                "entities": [f"TICKER:{sym}", f"IND:{ind}"],
                "symbols": sym,
                "categories": "TAI_CHINH",
                "intent_llm": sym,
                "intent_code": sym,
                "intent_source": "BOTH",
                "gold_status": "GOLD",
            }
        )
    publish_batch(batch1, date_str, "dev_alpha", "b01", storage)

    # Đợt 2 (Dev Beta): 500 bài viết (351 -> 850, trùng 150 bài với Alpha nhưng updated_at mới hơn)
    batch2 = []
    for i in range(351, 851):
        art_id = f"art_{i:04d}"
        sym = tickers[i % len(tickers)]
        ind = industries[i % len(industries)]
        batch2.append(
            {
                "article_id": art_id,
                "url": f"https://cafef.vn/{art_id}.chn",
                "title": f"Báo cáo cập nhật tình hình hoạt động {sym} mã số {art_id} [Beta]",
                "source_domain": "cafef.vn",
                "published_at": "2026-10-08T07:15:00Z",
                "updated_at": "2026-10-08T08:00:00Z",
                "dev_id": "dev_beta",
                "batch_id": "b02",
                "summary": f"Tóm tắt kết quả kinh doanh cập nhật cho {sym}.",
                "key_points": [f"Điểm nhấn 1 về {sym}", f"Điểm nhấn 2 về {sym}"],
                "implication": f"Tác động tài chính tích cực tới doanh nghiệp {sym}.",
                "sentiment": "pos",
                "time_sensitivity": "today",
                "citations": [f"Trích dẫn nguyên văn kiểm toán của {sym}"],
                "entities": [f"TICKER:{sym}", f"IND:{ind}"],
                "symbols": sym,
                "categories": "TAI_CHINH",
                "intent_llm": sym,
                "intent_code": sym,
                "intent_source": "BOTH",
                "gold_status": "GOLD",
            }
        )
    publish_batch(batch2, date_str, "dev_beta", "b02", storage)

    # Đợt 3 (Dev Gamma): 300 bài viết (701 -> 1000, trùng 150 bài với Beta)
    batch3 = []
    for i in range(701, 1001):
        art_id = f"art_{i:04d}"
        sym = tickers[i % len(tickers)]
        ind = industries[i % len(industries)]
        batch3.append(
            {
                "article_id": art_id,
                "url": f"https://cafef.vn/{art_id}.chn",
                "title": f"Báo cáo cập nhật tình hình hoạt động {sym} mã số {art_id} [Gamma]",
                "source_domain": "cafef.vn",
                "published_at": "2026-10-08T07:45:00Z",
                "updated_at": "2026-10-08T08:15:00Z",
                "dev_id": "dev_gamma",
                "batch_id": "b03",
                "summary": f"Tóm tắt kết quả kinh doanh kết phiên cho {sym}.",
                "key_points": [f"Điểm nhấn 1 về {sym}", f"Điểm nhấn 2 về {sym}"],
                "implication": f"Tác động tài chính tích cực tới doanh nghiệp {sym}.",
                "sentiment": "pos",
                "time_sensitivity": "today",
                "citations": [f"Trích dẫn nguyên văn kiểm toán của {sym}"],
                "entities": [f"TICKER:{sym}", f"IND:{ind}"],
                "symbols": sym,
                "categories": "TAI_CHINH",
                "intent_llm": sym,
                "intent_code": sym,
                "intent_source": "BOTH",
                "gold_status": "GOLD",
            }
        )
    publish_batch(batch3, date_str, "dev_gamma", "b03", storage)


def test_benchmark_1000_articles_consolidation_speed(tmp_path: Path):
    """Đo lường thời gian hợp nhất và khử trùng lặp 1.000 bài viết đạt dưới 1 giây.

    Args:
        tmp_path: Thư mục tạm độc lập do pytest cung cấp.
    """
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path / "lakehouse")
    date_str = "2026-10-08"

    # Bước chuẩn bị: Nạp 1.300 bản ghi thô (1.000 bài viết duy nhất)
    _build_perf_dataset(storage, date_str)

    # 1. Hợp nhất và khử trùng lặp qua DuckDB + Ghi Manifest
    t_start = time.perf_counter()
    consolidation_res = consolidate_dropzone(date_str=date_str, storage=storage)
    t_consolidation = time.perf_counter() - t_start

    # Kiểm tra tính toàn vẹn dữ liệu
    assert consolidation_res.total_scanned == 1300
    assert consolidation_res.unique_articles == 1000
    assert consolidation_res.partition_file != ""

    # Kiểm chứng cam kết SLA dưới 1.0 giây qua DuckDB
    assert t_consolidation < 1.0, f"Thời gian hợp nhất DuckDB vượt ngưỡng 1s SLA: {t_consolidation:.3f}s"


def test_benchmark_duckdb_vectorized_dedup_speed(tmp_path: Path):
    """Đo lường thời gian khử trùng lặp DuckDB độc lập trên 1.000 bài viết đạt dưới 1 giây.

    Args:
        tmp_path: Thư mục tạm độc lập do pytest cung cấp.
    """
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path / "lakehouse")
    date_str = "2026-10-08"

    _build_perf_dataset(storage, date_str)

    t0 = time.perf_counter()
    res = consolidate_dropzone(date_str=date_str, storage=storage)
    elapsed = time.perf_counter() - t0

    assert res.unique_articles == 1000
    assert elapsed < 1.0, f"Thời gian khử trùng lặp DuckDB vượt ngưỡng 1s: {elapsed:.3f}s"
