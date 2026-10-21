"""Command-line interface that drives the operations of the Lakehouse Data Plane."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add the project directory to sys.path so the source modules can be imported.
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
    """Resolve the root directory of the Lakehouse storage.

    Args:
        root_arg: Command-line value passed by the user.

    Returns:
        Path of the storage root directory.

    Raises:
        PermissionError: If the path belongs to the forbidden official SharePoint site.
    """
    from src.export.publisher import is_official_target

    if root_arg:
        target = Path(root_arg).resolve()
    else:
        env_root = os.getenv("NEWS_DATA_ROOT") or os.getenv("NEWS_SCAPE_PUBLISH_DIR")
        if env_root:
            target = Path(env_root).resolve()
        else:
            target = (PROJECT_ROOT.parent / "news-data").resolve()

    if is_official_target(target):
        raise PermissionError(
            f"Đích {target} thuộc site SharePoint chính thức (FRA - Data), bị cấm theo ADR-0023. "
            f"Chỉ được phép sử dụng sandbox FRA_DataIngestion."
        )
    return target


def handle_ingest(args: argparse.Namespace) -> int:
    """Handle the command that publishes an article batch into the Dropzone.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Process exit code (0 on success).
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
    """Handle the command that consolidates and deduplicates Dropzone data through DuckDB.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Process exit code (0 on success).
    """
    storage_root = resolve_storage_root(args.root)
    storage = LocalOneDriveStorageAdapter(storage_root)

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    auto_purge = not getattr(args, "no_purge", False)

    res = consolidate_dropzone(
        date_str=date_str,
        storage=storage,
        dropzone_pattern=args.dropzone_pattern,
        output_base=args.output_base,
        auto_purge=auto_purge,
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
    """Handle the command that verifies the integrity of a manifest file.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Process exit code (0 if valid, 1 on error).
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
    """Build the subcommands and arguments of the command-line tool.

    Returns:
        Configured ArgumentParser.
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
    p_cons.add_argument(
        "--no-purge",
        action="store_true",
        help="Không xóa tệp phân mảnh trong dropzone sau khi hợp nhất.",
    )
    p_cons.set_defaults(func=handle_consolidate)

    # Verify
    p_ver = subparsers.add_parser("verify", help="Kiểm chứng tính toàn vẹn của tệp Manifest.")
    p_ver.add_argument("--manifest", "-m", default="_manifest/latest.json", help="Đường dẫn tệp manifest.")
    p_ver.set_defaults(func=handle_verify)

    return parser


def main() -> int:
    """Run the Lakehouse CLI.

    Returns:
        Process exit code of the selected subcommand.
    """
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
