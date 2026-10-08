"""Quản lý xuất bản các gói dữ liệu bài viết vào vùng nạp Dropzone phi khóa."""

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

# Định nghĩa lược đồ Parquet chuẩn mực cho toàn bộ hệ thống Lakehouse
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
        ("symbols", pa.string()),
        ("categories", pa.string()),
        ("intent_llm", pa.string()),
        ("intent_code", pa.string()),
        ("intent_source", pa.string()),
        ("gold_status", pa.string()),
        ("raw_sha256", pa.string()),
    ]
)


def parse_date_components(date_str: str) -> tuple[str, str, str, str]:
    """Phân tách chuỗi ngày thành năm, tháng, ngày và chuỗi nén YYYYMMDD.

    Args:
        date_str: Chuỗi ngày ở định dạng 'YYYY-MM-DD' hoặc 'YYYYMMDD'.

    Returns:
        Tuple gồm 4 phần tử: (năm, tháng, ngày, chuỗi yyyymmdd).

    Raises:
        ValueError: Khi định dạng chuỗi ngày không hợp lệ.
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
    """Chuẩn hóa giá trị đầu vào thành danh sách chuỗi ký tự.

    Args:
        val: Giá trị cần chuyển đổi (list, tuple, chuỗi JSON hoặc chuỗi ngăn cách).

    Returns:
        Danh sách các chuỗi ký tự đã được cắt tỉa khoảng trắng.
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
        # Phân tách theo dòng hoặc dấu chấm phẩy
        if "\n" in raw:
            return [line.lstrip("-*• ").strip() for line in raw.splitlines() if line.strip()]
        if ";" in raw:
            return [item.strip() for item in raw.split(";") if item.strip()]
        return [raw]
    return [str(val)]


def sanitize_article_record(
    record: dict[str, Any],
    dev_id: str,
    batch_id: str,
    default_timestamp: str,
) -> dict[str, Any]:
    """Chuẩn hóa một bản ghi bài viết khớp với lược đồ LAKEHOUSE_ARTICLE_SCHEMA.

    Args:
        record: Từ điển dữ liệu bài viết ban đầu.
        dev_id: Mã định danh Dev hoặc Worker xuất bản.
        batch_id: Mã định danh lô bài viết.
        default_timestamp: Mốc thời gian mặc định dạng ISO 8601 UTC.

    Returns:
        Từ điển dữ liệu đã được làm sạch và điền đầy đủ các trường bắt buộc.
    """
    rec_dev = str(record.get("dev_id") or dev_id).strip()
    rec_batch = str(record.get("batch_id") or batch_id).strip()
    rec_updated = str(record.get("updated_at") or default_timestamp).strip()
    rec_pub = str(record.get("published_at") or default_timestamp).strip()

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
        "symbols": str(record.get("symbols") or "").strip().upper(),
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
    """Chuyển đổi danh sách bản ghi bài viết sang dữ liệu nhị phân Parquet nén ZSTD.

    Args:
        records: Danh sách từ điển dữ liệu bài viết.
        dev_id: Mã định danh Dev hoặc Worker xuất bản.
        batch_id: Mã định danh lô bài viết.
        schema: Lược đồ PyArrow áp dụng cho bảng.

    Returns:
        Chuỗi byte nhị phân định dạng Parquet.
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
    """Xuất bản một lô bài viết vào vùng nạp Dropzone dưới dạng tệp tin Parquet phân mảnh.

    Thực hiện quy trình tạo tên tệp duy nhất theo không gian tên riêng biệt để loại trừ
    100% nguy cơ tranh chấp khóa tệp và xung đột đồng bộ giữa nhiều Workers.

    Args:
        records: Danh sách từ điển dữ liệu bài viết cần xuất bản.
        date_str: Chuỗi ngày phân vùng (vd: '2026-10-08' hoặc '20261008').
        dev_id: Mã định danh duy nhất của Worker/Dev xuất bản (vd: 'dev_anpt').
        batch_id: Mã định danh lô dữ liệu (vd: 'b01').
        storage: Adapter giao tiếp với hệ thống lưu trữ.
        base_dir: Thư mục gốc của vùng nạp dropzone (mặc định 'dropzone').

    Returns:
        Đường dẫn tương đối của tệp tin Parquet đã xuất bản thành công.

    Raises:
        ValueError: Khi danh sách bản ghi rỗng hoặc thiếu thông tin định danh.
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
