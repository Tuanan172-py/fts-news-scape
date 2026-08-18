"""
Incremental re-derive driver — Bronze → Silver → version → package → catalog.

Khác `rederive_from_bronze.py` (full-scan, cho bump schema/parser): đây là chế độ
TĂNG DẦN cho vận hành liên tục (morninger). Dùng watermark `fetch_ts` (đơn điệu tăng
theo capture, rate-limited ~3s/bài) để CHỈ xử lý Bronze artifact MỚI hơn watermark.

Selection STRICT `>` (chỉ fetch_ts > watermark):
  - re-run nhàn rỗi → processed=0 (không tạo version UNCHANGED thừa).
  - file fetch_ts rỗng/corrupt → luôn được xử lý lại (retry raw_missing/corrupt).

Watermark lưu trong bảng `pipeline_state` (key `silver_watermark`). Sau mỗi lần chạy:
  - watermark_mới = max(fetch_ts) của các file xử lý THÀNH CÔNG (ok=True).
  - file lỗi (raw_missing, package invalid...) không đóng góp fetch_ts → bị quét lại
    chu kỳ sau.
  - checkpoint "đầy đủ" ⇔ không còn file nào có fetch_ts > watermark_mới (backlog = 0).
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from src.pipeline.run import process_meta

WATERMARK_KEY = "silver_watermark"
CHECKPOINT_KEY = "silver_checkpoint"


def _read_fetch_ts(meta_path: str) -> str:
    """Đọc `fetch_ts` từ meta.json (field nhỏ, đọc nhanh). Trả '' nếu lỗi/thiếu."""
    try:
        meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return ""
    return meta.get("fetch_ts", "") or ""


def iter_meta_paths(raw_dir: str = "data/raw_html") -> list[str]:
    """Tất cả *.meta.json dưới raw_dir, sắp xếp ổn định."""
    root = Path(raw_dir)
    if not root.exists():
        return []
    return sorted(str(p) for p in root.rglob("*.meta.json"))


def _should_process(fetch_ts: str, watermark: str) -> bool:
    """Quyết định xử lý 1 file: first-run (watermark='') xử lý hết; sau đó chỉ file
    MỚI hơn watermark (strict) hoặc file thiếu fetch_ts (retry)."""
    if not watermark:  # first run — xử lý toàn bộ
        return True
    if not fetch_ts:  # corrupt/thiếu fetch_ts — luôn retry
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
    """Xử lý tăng dần Bronze artifact MỚI hơn watermark. Trả summary dict.

    watermark=None → đọc từ pipeline_state (key silver_watermark); '' nghĩa là từ đầu.
    persist=True → ghi lại watermark + checkpoint vào pipeline_state.
    """
    if watermark is None:
        watermark = store.get_state(WATERMARK_KEY) or ""
    if not watermark:
        watermark = ""

    all_paths = iter_meta_paths(raw_dir)
    to_process = [p for p in all_paths if _should_process(_read_fetch_ts(p), watermark)]

    n = ok = held = 0
    ok_ts: list[str] = []
    by_state: dict[str, int] = {}
    for meta_path in to_process:
        n += 1
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
