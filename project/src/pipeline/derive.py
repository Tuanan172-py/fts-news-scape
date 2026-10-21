"""Orchestrate incremental derivation from Bronze to Silver and the Catalog, using a `fetch_ts` watermark to process only new Bronze files."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from src.core import paths
from src.core.stdio import force_utf8_stdio
from src.pipeline.run import process_meta

force_utf8_stdio()

WATERMARK_KEY = "silver_watermark"
CHECKPOINT_KEY = "silver_checkpoint"
DEFAULT_MAX_ATTEMPTS = 5      # ADR 0007 §2.2 — after this many attempts the file moves to dead-letter


def _prev_ts(ts: str) -> str:
    """Return the timestamp just BEFORE `ts` so the watermark does not swallow the failed file.

    `_should_process` compares strictly `fetch_ts > watermark`, so setting the watermark
    exactly to the failed file's timestamp would exclude that file from the next scan,
    which reproduces the article-loss defect being fixed.

    Args:
        ts: ISO timestamp with the fixed `+07:00` offset.

    Returns:
        ISO timestamp moved back by 1 second, or an empty string when unparsable (full
        rescan: expensive but never loses an article; bounded by the dead-letter threshold).
    """
    try:
        return (datetime.fromisoformat(ts) - timedelta(seconds=1)).isoformat(
            timespec="seconds")
    except (TypeError, ValueError):
        return ""


def _read_fetch_ts(meta_path: str) -> str:
    """Read the fetch_ts field from a .meta.json metadata file.

    Args:
        meta_path: Path to the .meta.json file.

    Returns:
        Article fetch timestamp string, or an empty string when the file is unreadable.
    """
    try:
        meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return ""
    return meta.get("fetch_ts", "") or ""


def iter_meta_paths(raw_dir: str | None = None) -> list[str]:
    """List all .meta.json files in the Bronze storage directory in a stable order.

    Args:
        raw_dir: Root directory of the raw Bronze data. Defaults to `paths.bronze_dir()`.

    Returns:
        Paths of the metadata files.
    """
    root = paths.resolve_data_path(raw_dir) if raw_dir else paths.bronze_dir()
    if not root.exists():
        return []
    return sorted(str(p) for p in root.rglob("*.meta.json"))


def _should_process(fetch_ts: str, watermark: str) -> bool:
    """Check whether a file needs derivation.

    Args:
        fetch_ts: Fetch timestamp of the file.
        watermark: Current watermark; empty means process everything.

    Returns:
        True if the file must be processed.
    """
    if not watermark:
        return True
    if not fetch_ts:
        return True
    return fetch_ts > watermark


def rederive_incremental(
    store,
    *,
    raw_dir: str | None = None,
    silver_dir: str | None = None,
    package_dir: str | None = None,
    watermark: str | None = None,
    t_content: int = 6,
    t_template: int = 12,
    do_enqueue: bool = True,
    persist: bool = True,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> dict:
    """Derive incrementally the Bronze articles newer than the watermark.

    Args:
        store: ArticleStore object that manages the database.
        raw_dir: Directory of the raw Bronze data.
        silver_dir: Directory that stores the Silver output.
        package_dir: Directory that stores the Work Package files.
        watermark: Timestamp to start scanning from; None reads it from the database.
        t_content: Content distance threshold.
        t_template: Layout structure distance threshold.
        do_enqueue: Allow enqueuing articles into the work_items queue.
        persist: Allow saving the new watermark and the failure ledger to the database.
        max_attempts: Number of failed derive attempts before the file moves to dead-letter
            and stops blocking the watermark (ADR 0007).

    Returns:
        Dict summarizing processed counts, states and the new watermark.
    """
    if watermark is None:
        watermark = store.get_state(WATERMARK_KEY) or ""
    if not watermark:
        watermark = ""

    if persist:
        store.normalize_silver_failure_keys()

    raw_path_res = str(paths.resolve_data_path(raw_dir) if raw_dir else paths.bronze_dir())
    silver_path_res = str(paths.resolve_data_path(silver_dir) if silver_dir else paths.silver_dir())
    package_path_res = str(paths.resolve_data_path(package_dir) if package_dir else paths.work_packages_dir())

    print(f"[derive] Quét thư mục Bronze '{raw_path_res}' (watermark={watermark or 'bắt đầu'})...", flush=True)
    all_paths = iter_meta_paths(raw_path_res)
    # Read fetch_ts once per file and reuse it to avoid repeated reads and parses per cycle.
    ts_by_path = {p: _read_fetch_ts(p) for p in all_paths}
    to_process = [p for p in all_paths if _should_process(ts_by_path[p], watermark)]
    print(f"[derive] Quét xong {len(all_paths)} Bronze files: tìm thấy {len(to_process)} bài mới cần chuyển lên Silver.", flush=True)

    n = ok = held = failed = 0
    ok_ts: list[str] = []
    by_state: dict[str, int] = {}
    for idx, meta_path in enumerate(to_process):
        n += 1
        if (idx + 1) % 25 == 0 or idx == len(to_process) - 1:
            print(f"  [derive] Đang xử lý: [{idx + 1}/{len(to_process)}] bài...", flush=True)
        ft = ts_by_path.get(meta_path, "")
        try:
            res = process_meta(
                store,
                meta_path,
                silver_dir=silver_path_res,
                package_dir=package_path_res,
                t_content=t_content,
                t_template=t_template,
                do_enqueue=do_enqueue,
            )
        except Exception as e:  # noqa: BLE001 — non-fatal per article (I5)
            logger.error("[derive] process failed {}: {}", meta_path, e)
            failed += 1
            if persist:
                store.record_silver_failure(meta_path, ft, f"{type(e).__name__}: {e}",
                                            max_attempts)
            continue
        state = (
            res.get("state") or "raw_missing"
        )  # raw_missing returns early without a state
        by_state[state] = by_state.get(state, 0) + 1
        # The "ok" flag of process_meta only reports a valid package. An article with
        # silver_ok=False must not count as success, or the watermark would advance past it
        # and it would never be derived again (ADR 0007 §1).
        succeeded = bool(res["ok"]) and bool(res.get("silver_ok", True))
        if succeeded:
            ok += 1
            if ft:
                ok_ts.append(ft)
            if persist:
                store.clear_silver_failure(meta_path)
        else:
            failed += 1
            if persist:
                reason = "; ".join(str(x) for x in (res.get("errors") or [])[:2]) \
                    or f"state={state} silver_ok={res.get('silver_ok')} pkg_ok={res['ok']}"
                store.record_silver_failure(meta_path, ft, reason, max_attempts,
                                            url_title_hash=res.get("article_id", ""))
        if res.get("enqueue_status") == "held":
            held += 1

    # The watermark is a low-water mark: it never passes a failure that is not yet dead-letter.
    blocking_ts = store.blocking_silver_failure_ts() if persist else ""
    candidate = max(ok_ts) if ok_ts else watermark
    if blocking_ts:
        # Step back to just BEFORE the earliest failure so the next cycle selects it again.
        watermark_new = min(candidate, _prev_ts(blocking_ts)) if candidate else ""
    else:
        watermark_new = candidate
    latest = max(ts_by_path.values(), default="")
    backlog = sum(1 for p in all_paths if (ft := ts_by_path[p]) and ft > watermark_new)
    checkpoint_reached = backlog == 0

    if persist:
        store.set_state(WATERMARK_KEY, watermark_new)
        if checkpoint_reached:
            store.set_state(CHECKPOINT_KEY, watermark_new)

    blocking_n, dead_n = store.count_silver_failures() if persist else (0, 0)
    summary = {
        "processed": n,
        "ok": ok,
        "failed": failed,
        "held": held,
        "states": by_state,
        "watermark_prev": watermark,
        "watermark_new": watermark_new,
        "latest_fetch_ts": latest,
        "backlog": backlog,
        "checkpoint_reached": checkpoint_reached,
        "blocking_failures": blocking_n,
        "dead_letter": dead_n,
    }
    logger.info(
        "[derive] done: {} processed, {} ok, {} failed, {} held; watermark {} -> {}; "
        "backlog={} checkpoint={} blocking={} dead_letter={}",
        n,
        ok,
        failed,
        held,
        watermark,
        watermark_new,
        backlog,
        checkpoint_reached,
        blocking_n,
        dead_n,
    )
    if dead_n:
        logger.error(
            "[derive] {} tệp Bronze đã dead-letter — nội dung KHÔNG lên được Silver. "
            "Kiểm tra bảng silver_failures.", dead_n)
    return summary
