"""Giao diện dòng lệnh CLI điều phối các hoạt động của Lakehouse Data Plane."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Thêm thư mục project vào sys.path để nạp các module nguồn
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.stdio import force_utf8_stdio
force_utf8_stdio()

from src.lakehouse.consolidator import consolidate_dropzone
from src.lakehouse.ingest import publish_batch
from src.lakehouse.manifest import verify_manifest
from src.lakehouse.storage import LocalOneDriveStorageAdapter


def resolve_storage_root(root_arg: str | None) -> Path:
    """Xác định đường dẫn thư mục gốc của kho dữ liệu Lakehouse.

    Args:
        root_arg: Giá trị tham số dòng lệnh do người dùng truyền vào.

    Returns:
        Đối tượng Path trỏ tới thư mục gốc kho dữ liệu.
    """
    if root_arg:
        return Path(root_arg).resolve()
    env_root = os.getenv("NEWS_DATA_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return (PROJECT_ROOT.parent / "news-data").resolve()


def handle_ingest(args: argparse.Namespace) -> int:
    """Xử lý lệnh xuất bản gói bài viết vào vùng nạp Dropzone.

    Args:
        args: Các tham số dòng lệnh đã phân tích cú pháp.

    Returns:
        Mã trạng thái kết thúc tiến trình (0 nếu thành công).
    """
    storage_root = resolve_storage_root(args.root)
    storage = LocalOneDriveStorageAdapter(storage_root)

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"Lỗi: Không tìm thấy tệp dữ liệu đầu vào: {input_path}", file=sys.stderr)
        return 1

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        records = data.get("records") or data.get("articles") or [data]
    elif isinstance(data, list):
        records = data
    else:
        print("Lỗi: Định dạng tệp JSON không hợp lệ.", file=sys.stderr)
        return 1

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dev_id = args.dev_id or os.getenv("DEV_ID") or "dev_default"
    batch_id = args.batch_id or uuid.uuid4().hex[:8]

    saved_rel = publish_batch(
        records=records,
        date_str=date_str,
        dev_id=dev_id,
        batch_id=batch_id,
        storage=storage,
    )

    print(f"Đã xuất bản {len(records)} bài viết vào: {saved_rel}")
    return 0


def handle_consolidate(args: argparse.Namespace) -> int:
    """Xử lý lệnh hợp nhất và khử trùng lặp dữ liệu Dropzone qua DuckDB.

    Args:
        args: Các tham số dòng lệnh đã phân tích cú pháp.

    Returns:
        Mã trạng thái kết thúc tiến trình (0 nếu thành công).
    """
    storage_root = resolve_storage_root(args.root)
    storage = LocalOneDriveStorageAdapter(storage_root)

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    res = consolidate_dropzone(
        date_str=date_str,
        storage=storage,
        dropzone_pattern=args.dropzone_pattern,
        output_base=args.output_base,
    )

    print(f"Hoàn tất hợp nhất dữ liệu ngày: {res.date_str}")
    print(f"- Số bản ghi quét: {res.total_scanned}")
    print(f"- Số bài viết duy nhất: {res.unique_articles}")
    print(f"- Tệp phân vùng: {res.partition_file}")
    print(f"- Tệp kê khai manifest: {res.manifest_file}")
    print(f"- Mã băm SHA-256: {res.sha256}")
    print(f"- Thời gian thực thi: {res.elapsed_ms:.2f} ms")
    return 0


def handle_verify(args: argparse.Namespace) -> int:
    """Xử lý lệnh kiểm chứng tính toàn vẹn của tệp kê khai Manifest.

    Args:
        args: Các tham số dòng lệnh đã phân tích cú pháp.

    Returns:
        Mã trạng thái kết thúc tiến trình (0 nếu hợp lệ, 1 nếu có lỗi).
    """
    storage_root = resolve_storage_root(args.root)
    storage = LocalOneDriveStorageAdapter(storage_root)

    manifest_rel = args.manifest or "_manifest/latest.json"

    try:
        report = verify_manifest(manifest_rel, storage)
    except FileNotFoundError as e:
        print(f"Lỗi: {e}", file=sys.stderr)
        return 1

    if report["valid"]:
        print(f"Kiểm chứng thành công: {manifest_rel}")
        print(f"- Số phân vùng: {report['total_partitions']}")
        print(f"- Tổng số dòng: {report['total_rows']}")
        return 0

    print(f"Kiểm chứng thất bại: {manifest_rel}", file=sys.stderr)
    for err in report["mismatches"]:
        print(f"  [X] {err}", file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    """Thiết lập cấu trúc các lệnh con và tham số của công cụ dòng lệnh.

    Returns:
        Đối tượng ArgumentParser đã được cấu hình đầy đủ.
    """
    parser = argparse.ArgumentParser(
        description="Giao diện quản trị Lakehouse Data Plane phân tán.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--root",
        help="Đường dẫn thư mục gốc kho dữ liệu Lakehouse (mặc định đọc NEWS_DATA_ROOT).",
    )

    subparsers = parser.add_subparsers(dest="command", required=True, help="Các lệnh thực thi")

    # Ingest / Push
    p_ingest = subparsers.add_parser("ingest", help="Xuất bản lô bài viết vào vùng nạp Dropzone.")
    p_ingest.add_argument("--input", "-i", required=True, help="Đường dẫn tệp JSON dữ liệu bài viết.")
    p_ingest.add_argument("--date", "-d", help="Chuỗi ngày nghiệp vụ (YYYY-MM-DD hoặc YYYYMMDD).")
    p_ingest.add_argument("--dev-id", help="Mã định danh duy nhất của Dev/Worker.")
    p_ingest.add_argument("--batch-id", help="Mã định danh lô bài viết.")
    p_ingest.set_defaults(func=handle_ingest)

    # Consolidate
    p_cons = subparsers.add_parser("consolidate", help="Hợp nhất và khử trùng lặp dữ liệu qua DuckDB.")
    p_cons.add_argument("--date", "-d", help="Chuỗi ngày nghiệp vụ cần hợp nhất (YYYY-MM-DD).")
    p_cons.add_argument(
        "--dropzone-pattern",
        default="dropzone/*/*/*/*.parquet",
        help="Mẫu tìm kiếm tệp Parquet trong dropzone.",
    )
    p_cons.add_argument(
        "--output-base",
        default="parquet/articles",
        help="Thư mục gốc lưu trữ phân vùng Parquet.",
    )
    p_cons.set_defaults(func=handle_consolidate)

    # Verify
    p_ver = subparsers.add_parser("verify", help="Kiểm chứng tính toàn vẹn của tệp Manifest.")
    p_ver.add_argument("--manifest", "-m", default="_manifest/latest.json", help="Đường dẫn tệp manifest.")
    p_ver.set_defaults(func=handle_verify)

    return parser


def main() -> int:
    """Điểm nhập chính cho công cụ dòng lệnh Lakehouse CLI.

    Returns:
        Mã kết thúc tiến trình.
    """
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
