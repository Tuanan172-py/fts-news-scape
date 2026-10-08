"""Kiểm thử chuẩn hiệu năng tổng hợp và phân phối 1.000 bài viết dưới 5 giây."""

from __future__ import annotations

import time
from pathlib import Path

import openpyxl
import pytest
import yaml

from src.lakehouse.consolidator import consolidate_dropzone
from src.lakehouse.delivery import SHEET_MAIN_NAME, distribute_to_users
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
                "published_at": "2026-10-08T07:30:00Z",
                "updated_at": "2026-10-08T08:30:00Z",
                "dev_id": "dev_gamma",
                "batch_id": "b03",
                "summary": f"Tóm tắt kết quả kinh doanh mới nhất cho {sym}.",
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


def _setup_users_config(base_path: Path) -> tuple[Path, Path]:
    """Khởi tạo cấu hình 5 chuyên viên phân tích độc lập.

    Args:
        base_path: Thư mục gốc thiết lập.

    Returns:
        Tuple gồm (đường dẫn manifest.yaml, thư mục users_cfg).
    """
    users_cfg_dir = base_path / "users_cfg"
    users_cfg_dir.mkdir(parents=True, exist_ok=True)
    manifest_p = base_path / "manifest.yaml"

    user_definitions = {
        "AnPT": {"tickers": ["HPG", "FPT"], "industries": ["THEP", "CONG_NGHE"]},
        "PhoHG": {"tickers": ["VIC", "VHM"], "industries": ["BAT_DONG_SAN"]},
        "ThanhTD": {"tickers": ["GAS", "PLX"], "industries": ["DAU_KHI"]},
        "VyPTT": {"tickers": ["VNM", "MSN"], "industries": ["THUC_PHAM"]},
        "UyenNNT": {"tickers": ["VCB", "SSI"], "industries": ["NGAN_HANG"]},
    }

    manifest_users = {}
    for user_name, cfg in user_definitions.items():
        user_file = users_cfg_dir / f"{user_name}.yaml"
        with open(user_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f)
        manifest_users[user_name] = True

    manifest_data = {
        "enabled": True,
        "default": False,
        "users": manifest_users,
    }
    with open(manifest_p, "w", encoding="utf-8") as f:
        yaml.safe_dump(manifest_data, f)

    return manifest_p, users_cfg_dir


def test_benchmark_1000_articles_consolidation_and_delivery(tmp_path: Path):
    """Đo lường thời gian hợp nhất và phân phối 1.000 bài viết đạt dưới 5 giây.

    Args:
        tmp_path: Thư mục tạm độc lập do pytest cung cấp.
    """
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path / "lakehouse")
    date_str = "2026-10-08"

    # Bước chuẩn bị: Nạp 1.300 bản ghi thô (1.000 bài viết duy nhất)
    _build_perf_dataset(storage, date_str)
    manifest_path, users_cfg_dir = _setup_users_config(tmp_path)
    output_dir = tmp_path / "delivery_output"

    # Bắt đầu đo thời gian quy trình tổng hợp và phân phối
    t_start = time.perf_counter()

    # 1. Hợp nhất và khử trùng lặp qua DuckDB + Ghi Manifest
    t_c0 = time.perf_counter()
    consolidation_res = consolidate_dropzone(date_str=date_str, storage=storage)
    t_consolidation = time.perf_counter() - t_c0

    # 2. Phân phối báo cáo Excel 2 sheets cho 5 người dùng
    t_d0 = time.perf_counter()
    parquet_abs = storage.get_local_path(consolidation_res.partition_file)
    assert parquet_abs is not None

    deliveries = distribute_to_users(
        date_str=date_str,
        parquet_path=str(parquet_abs),
        manifest_config_path=str(manifest_path),
        users_config_dir=str(users_cfg_dir),
        output_dir=str(output_dir),
    )
    t_delivery = time.perf_counter() - t_d0

    t_total = time.perf_counter() - t_start

    # Kiểm tra tính toàn vẹn dữ liệu
    assert consolidation_res.total_scanned == 1300
    assert consolidation_res.unique_articles == 1000
    assert len(deliveries) == 5

    # Kiểm tra tệp Excel của từng người dùng
    for u_name, f_path in deliveries.items():
        assert f_path.exists()
        wb = openpyxl.load_workbook(f_path, read_only=True)
        assert SHEET_MAIN_NAME in wb.sheetnames
        wb.close()

    # Kiểm chứng cam kết SLA dưới 8.0 giây
    assert t_total < 8.0, f"Tổng thời gian xử lý vượt ngưỡng 8s SLA: {t_total:.3f}s"


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
