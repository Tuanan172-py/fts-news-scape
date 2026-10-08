"""Động cơ hợp nhất và khử trùng lặp dữ liệu Lakehouse sử dụng DuckDB."""

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
    """Kết quả tổng hợp và khử trùng lặp dữ liệu bài viết.

    Attributes:
        date_str: Chuỗi ngày xử lý nghiệp vụ.
        total_scanned: Tổng số bản ghi thô được quét từ các tệp nạp.
        unique_articles: Số lượng bản ghi bài viết duy nhất sau khi khử trùng lặp.
        partition_file: Đường dẫn tương đối của tệp tin phân vùng Parquet thành phẩm.
        manifest_file: Đường dẫn tương đối của tệp tin kê khai manifest theo ngày.
        sha256: Mã băm SHA-256 của tệp tin phân vùng Parquet.
        elapsed_ms: Thời gian thực thi đo bằng mili giây.
        partitions: Danh sách các thực thể phân vùng trong bản kê khai.
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
) -> ConsolidationResult:
    """Quét vùng nạp Dropzone, khử trùng lặp theo article_id và kết xuất phân vùng Parquet.

    Sử dụng động cơ DuckDB với mệnh đề QUALIFY ROW_NUMBER() OVER (...) để ưu tiên bản ghi
    có mốc updated_at mới nhất. Tự động gộp với tệp phân vùng đã tồn tại trước đó để thực
    hiện nạp gia tăng (incremental compaction) an toàn.

    Args:
        date_str: Chuỗi ngày nghiệp vụ cần tổng hợp (vd: '2026-10-08' hoặc '20261008').
        storage: Adapter giao tiếp hệ thống lưu trữ.
        dropzone_pattern: Mẫu tìm kiếm các tệp tin trong vùng nạp Dropzone.
        output_base: Thư mục gốc chứa kho Parquet phân vùng (mặc định 'parquet/articles').

    Returns:
        Đối tượng ConsolidationResult chứa thống kê tổng hợp và siêu dữ liệu kiểm toán.

    Raises:
        ValueError: Khi không có dữ liệu nào để xử lý cho ngày yêu cầu.
    """
    t_start = time.perf_counter()
    year, month, day, yyyymmdd = parse_date_components(date_str)

    # Thu thập danh sách các tệp tin trong dropzone
    date_specific_prefix = f"dropzone/{year}/{month}/{day}"
    all_dropzone_files = storage.list_files(dropzone_pattern)
    matched_dropzone = [
        f for f in all_dropzone_files if f.startswith(date_specific_prefix)
    ]

    # Nếu không có tệp nào khớp tiền tố ngày cụ thể, kiểm tra các tệp dropzone tìm thấy
    if not matched_dropzone and all_dropzone_files:
        # Lọc các tệp chứa chuỗi yyyymmdd trong tên tệp
        matched_dropzone = [f for f in all_dropzone_files if yyyymmdd in f]

    # Kiểm tra phân vùng hiện có trong kho để nạp gia tăng
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

    # Khởi tạo kết nối DuckDB trong tiến trình
    con = duckdb.connect()
    try:
        con.execute("PRAGMA threads = 4;")
        con.execute("PRAGMA memory_limit = '2GB';")

        # Kiểm tra xem có thể dùng đường dẫn cục bộ hay đọc nhị phân vào PyArrow Table
        local_paths: list[str] = []
        for rel_f in all_input_files:
            loc = storage.get_local_path(rel_f)
            if loc is not None and loc.is_file():
                local_paths.append(loc.as_posix())

        if len(local_paths) == len(all_input_files):
            # Tối ưu hóa: Đọc trực tiếp các tệp tin trên đĩa qua vectorized engine của DuckDB
            source_expr = "read_parquet(?)"
            query_params = [local_paths]
        else:
            # Fallback: Đọc dữ liệu qua adapter read_bytes và nạp vào PyArrow Table
            arrow_tables: list[pa.Table] = []
            for rel_f in all_input_files:
                b = storage.read_bytes(rel_f)
                arrow_tables.append(pq.read_table(io.BytesIO(b)))
            combined_arrow = pa.concat_tables(arrow_tables)
            con.register("raw_lakehouse_input", combined_arrow)
            source_expr = "raw_lakehouse_input"
            query_params = []

        # Thực thi truy vấn khử trùng lặp có thứ tự ưu tiên
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

        # Chuyển kết quả sang dữ liệu Parquet nén ZSTD
        buf = io.BytesIO()
        pq.write_table(result_arrow, buf, compression="ZSTD")
        parquet_bytes = buf.getvalue()


        # Ghi tệp phân vùng nguyên tử qua storage adapter
        target_partition_rel = f"{output_base}/year={year}/month={month}/part-{yyyymmdd}.parquet"
        saved_partition_path = storage.write_atomic(target_partition_rel, parquet_bytes)
        sha256_hash = hashlib.sha256(parquet_bytes).hexdigest()

        # Tạo bản ghi manifest và cập nhật latest.json
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
