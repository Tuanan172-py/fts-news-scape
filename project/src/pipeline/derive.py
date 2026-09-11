"""Trình điều phối tinh chế dữ liệu tăng dần từ Bronze sang Silver và Catalog.

Sử dụng cơ chế điểm mốc thời gian (watermark fetch_ts) để chỉ xử lý các
tệp dữ liệu tầng Bronze mới phát sinh, cập nhật bài viết tầng Silver và đưa vào hàng đợi.
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from src.pipeline.run import process_meta

WATERMARK_KEY = "silver_watermark"
CHECKPOINT_KEY = "silver_checkpoint"


def _read_fetch_ts(meta_path: str) -> str:
    """Đọc trường fetch_ts từ tệp tin siêu dữ liệu .meta.json.

    Args:
        meta_path: Đường dẫn tới tệp .meta.json.

    Returns:
        Chuỗi thời gian thu thập bài viết, hoặc rỗng nếu tệp lỗi.
    """
    try:
        meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return ""
    return meta.get("fetch_ts", "") or ""


def iter_meta_paths(raw_dir: str = "data/raw_html") -> list[str]:
    """Liệt kê toàn bộ các tệp .meta.json trong thư mục lưu trữ Bronze theo thứ tự ổn định.

    Args:
        raw_dir: Đường dẫn thư mục gốc chứa dữ liệu thô Bronze.

    Returns:
        Danh sách đường dẫn các tệp siêu dữ liệu.
    """
    root = Path(raw_dir)
    if not root.exists():
        return []
    return sorted(str(p) for p in root.rglob("*.meta.json"))


def _should_process(fetch_ts: str, watermark: str) -> bool:
    """Kiểm tra xem tệp tin có thỏa mãn điều kiện cần tinh chế hay không."""
    if not watermark:
        return True
    if not fetch_ts:
        return True
    return fetch_ts > watermark


def rederive_incremental(
    store,
    *,
    raw_dir: str = "data/raw_html",
    silver_dir: str = "data/silver",
    package_dir: str = "data/work_packages",
    watermark: str | None = None,
    t_content: int = 6,
    t_template: int = 12,
    do_enqueue: bool = True,
    persist: bool = True,
) -> dict:
    """Thực hiện tinh chế tăng dần các bài viết Bronze mới hơn mốc watermark.

    Args:
        store: Đối tượng ArticleStore quản lý cơ sở dữ liệu.
        raw_dir: Thư mục chứa dữ liệu thô Bronze.
        silver_dir: Thư mục lưu trữ kết quả Silver.
        package_dir: Thư mục lưu trữ gói công việc Work Package.
        watermark: Mốc thời gian bắt đầu quét (nếu None sẽ lấy từ cơ sở dữ liệu).
        t_content: Ngưỡng khoảng cách nội dung.
        t_template: Ngưỡng khoảng cách cấu trúc giao diện.
        do_enqueue: Cờ cho phép đưa bài vào hàng đợi work_items.
        persist: Cờ cho phép lưu lại mốc watermark mới vào cơ sở dữ liệu.

    Returns:
        Từ điển tổng kết số lượng xử lý, trạng thái và mốc watermark mới.
    """
    if watermark is None:
        watermark = store.get_state(WATERMARK_KEY) or ""
    if not watermark:
        watermark = ""

    print(f"🔄 [derive] Đang quét thư mục Bronze '{raw_dir}' (watermark={watermark or 'bắt đầu'})...", flush=True)
    all_paths = iter_meta_paths(raw_dir)
    to_process = [p for p in all_paths if _should_process(_read_fetch_ts(p), watermark)]
    print(f"📦 [derive] Quét xong {len(all_paths)} Bronze files: tìm thấy {len(to_process)} bài mới cần chuyển lên Silver.", flush=True)

    n = ok = held = 0
    ok_ts: list[str] = []
    by_state: dict[str, int] = {}
    for idx, meta_path in enumerate(to_process):
        n += 1
        if (idx + 1) % 25 == 0 or idx == len(to_process) - 1:
            print(f"  ⚡ [derive] Đang xử lý: [{idx + 1}/{len(to_process)}] bài...", flush=True)
        try:
            res = process_meta(
                store,
                meta_path,
                silver_dir=silver_dir,
                package_dir=package_dir,
                t_content=t_content,
                t_template=t_template,
                do_enqueue=do_enqueue,
            )
        except Exception as e:  # noqa: BLE001 — non-fatal per bài (I5)
            logger.error("[derive] process failed {}: {}", meta_path, e)
            continue
        state = (
            res.get("state") or "raw_missing"
        )  # raw_missing trả early-return không có state
        by_state[state] = by_state.get(state, 0) + 1
        if res["ok"]:
            ok += 1
            ft = _read_fetch_ts(meta_path)
            if ft:
                ok_ts.append(ft)
        if res.get("enqueue_status") == "held":
            held += 1

    watermark_new = max(ok_ts) if ok_ts else watermark
    latest = max((_read_fetch_ts(p) for p in all_paths), default="")
    backlog = sum(
        1 for p in all_paths if (ft := _read_fetch_ts(p)) and ft > watermark_new
    )
    checkpoint_reached = backlog == 0

    if persist:
        store.set_state(WATERMARK_KEY, watermark_new)
        if checkpoint_reached:
            store.set_state(CHECKPOINT_KEY, watermark_new)

    summary = {
        "processed": n,
        "ok": ok,
        "held": held,
        "states": by_state,
        "watermark_prev": watermark,
        "watermark_new": watermark_new,
        "latest_fetch_ts": latest,
        "backlog": backlog,
        "checkpoint_reached": checkpoint_reached,
    }
    logger.info(
        "[derive] done: {} processed, {} ok, {} held; watermark {} -> {}; "
        "backlog={} checkpoint={}",
        n,
        ok,
        held,
        watermark,
        watermark_new,
        backlog,
        checkpoint_reached,
    )
    return summary
