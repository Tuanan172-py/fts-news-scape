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

    Hỗ trợ di chuyển cả các tệp đơn lẻ (<aid>.task.json) và các tệp mini-batch
    (batch_*.task.json) khi toàn bộ các bài viết cấu thành đã đạt chuẩn DoD.

    Args:
        article_ids: Danh sách các mã bài viết cần chuyển lưu trữ.
        task_dir: Thư mục chứa các tệp tác vụ đang hoạt động.
        archive_date: Chuỗi ngày lưu trữ định dạng 'YYYYMMDD'.

    Returns:
        Số lượng gói tác vụ đã di chuyển lưu trữ thành công.
    """
    cnt = 0
    task_dir = Path(task_dir)
    if not archive_date:
        archive_date = datetime.now(VN_TZ).strftime("%Y%m%d")

    target_dir = task_dir / "archive" / archive_date
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Di chuyển các tệp task đơn lẻ
    for aid in article_ids:
        if archive_task_packet(aid, task_dir, archive_date):
            cnt += 1

    # 2. Quét và di chuyển các tệp batch packet nếu các bài viết bên trong đã xử lý xong
    completed_set = set(article_ids)
    import json
    for batch_file in task_dir.glob("batch_*.task.json"):
        try:
            with open(batch_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            tasks = data.get("tasks", [])
            if tasks and all(t.get("article_id") in completed_set for t in tasks):
                dest = target_dir / batch_file.name
                shutil.move(str(batch_file), str(dest))
                logger.debug("[archive] moved batch {} -> {}", batch_file.name, dest)
                cnt += 1
        except Exception as e:
            logger.warning("[archive] failed to inspect/move batch {}: {}", batch_file.name, e)

    return cnt
