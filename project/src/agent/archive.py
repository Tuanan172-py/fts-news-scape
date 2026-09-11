"""Quản lý vòng đời và lưu trữ các gói tác vụ (Task Packets) sau khi nạp thành công.

Cung cấp các hàm di chuyển các tệp task.json đã hoàn tất vào thư mục lưu trữ archive
theo phân cấp ngày tháng nhằm giữ gọn hàng đợi tác vụ đang hoạt động.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.core.models import VN_TZ


def archive_task_packet(article_id: str, task_dir: str | Path,
                        archive_date: str | None = None) -> Path | None:
    """Di chuyển một tệp gói tác vụ task.json vào thư mục lưu trữ theo ngày.

    Args:
        article_id: Mã định danh của bài viết.
        task_dir: Thư mục chứa các tệp tác vụ đang hoạt động.
        archive_date: Chuỗi ngày lưu trữ định dạng 'YYYYMMDD' (nếu None lấy ngày hiện tại).

    Returns:
        Đường dẫn Path tới tệp đích đã lưu trữ, hoặc None nếu tệp nguồn không tồn tại.
    """
    task_dir = Path(task_dir)
    src_file = task_dir / f"{article_id}.task.json"
    if not src_file.is_file():
        return None

    if not archive_date:
        archive_date = datetime.now(VN_TZ).strftime("%Y%m%d")

    target_dir = task_dir / "archive" / archive_date
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"{article_id}.task.json"

    try:
        shutil.move(str(src_file), str(target_file))
        logger.debug("[archive] moved {} -> {}", src_file.name, target_file)
        return target_file
    except Exception as e:
        logger.warning("[archive] failed to move {}: {}", src_file.name, e)
        return None


def archive_completed_tasks(article_ids, task_dir: str | Path,
                            archive_date: str | None = None) -> int:
    """Di chuyển hàng loạt các gói tác vụ đã hoàn thành sang thư mục lưu trữ.

    Args:
        article_ids: Danh sách các mã bài viết cần chuyển lưu trữ.
        task_dir: Thư mục chứa các tệp tác vụ đang hoạt động.
        archive_date: Chuỗi ngày lưu trữ định dạng 'YYYYMMDD'.

    Returns:
        Số lượng gói tác vụ đã di chuyển lưu trữ thành công.
    """
    cnt = 0
    if not archive_date:
        archive_date = datetime.now(VN_TZ).strftime("%Y%m%d")
    for aid in article_ids:
        if archive_task_packet(aid, task_dir, archive_date):
            cnt += 1
    return cnt
