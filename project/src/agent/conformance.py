"""Chấm độ phù hợp của một provider với bộ vàng và với mức agy đã đo (ADR 0017 D7)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agent.article_contract import parse_and_validate

MARGIN = 0.05
METRICS = ("agree_sn", "agree_ts", "tic_f1")


def _load(path: Path) -> Any:
    """Đọc một tệp JSON UTF-8.

    Args:
        path: Đường dẫn tệp.

    Returns:
        Đối tượng JSON đã phân tích.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def score_outputs(output_dir: Path, task_dir: Path, gold: dict[str, dict],
                  batch_ids: list[str]) -> dict[str, Any]:
    """Chấm đầu ra thô của các lô theo bộ vàng.

    Args:
        output_dir: Thư mục chứa `<lô>.output.json`.
        task_dir: Thư mục chứa `<lô>.task.json` và `<lô>.map.json`.
        gold: Bộ vàng, khoá là `article_id`, giá trị có `sn`, `ts`, `tic`.
        batch_ids: Mã các lô cần chấm.

    Returns:
        Từ điển số đo: số bản ghi thô, số bị từ chối, id thiếu, độ khớp `sn`, `ts`,
        F1 của tập TIC, và số bài vàng được chấm.
    """
    raw = rejected = missing = 0
    hit_sn = hit_ts = scored = 0
    tp = fp = fn = 0

    for batch_id in batch_ids:
        packet = _load(task_dir / f"{batch_id}.task.json")
        index = _load(task_dir / f"{batch_id}.map.json").get("index") or {}
        text = (output_dir / f"{batch_id}.output.json").read_text(encoding="utf-8")
        result = parse_and_validate(text, packet)
        raw += result.counters.get("raw_records", 0)
        rejected += len(result.errors)
        missing += len(index) - len(result.records)

        for local_i, article_id in index.items():
            truth = gold.get(str(article_id))
            if truth is None:
                continue
            scored += 1
            rec = result.records.get(int(local_i))
            predicted = {s.upper() for s, g in (rec["e"] if rec else []) if g == "TIC"}
            expected = {t.upper() for t in truth.get("tic", [])}
            tp += len(predicted & expected)
            fp += len(predicted - expected)
            fn += len(expected - predicted)
            if rec and rec["sn"] == truth.get("sn"):
                hit_sn += 1
            if rec and rec["ts"] == truth.get("ts"):
                hit_ts += 1

    denom = 2 * tp + fp + fn
    return {
        "records_raw": raw,
        "records_rejected": rejected,
        "reject_rate": rejected / raw if raw else 1.0,
        "missing_ids": missing,
        "scored": scored,
        "agree_sn": hit_sn / scored if scored else 0.0,
        "agree_ts": hit_ts / scored if scored else 0.0,
        "tic_f1": (2 * tp / denom) if denom else 1.0,
    }


def check_against_baseline(candidate: dict[str, Any], baseline: dict[str, Any],
                           margin: float = MARGIN) -> list[str]:
    """So số đo của provider ứng viên với mức agy đã ghi.

    Điều kiện đạt: không bản ghi bị từ chối, không thiếu id, và mỗi độ khớp không thấp
    hơn mức agy trừ `margin`.

    Args:
        candidate: Số đo của provider ứng viên.
        baseline: Số đo agy trên cùng bộ vàng.
        margin: Biên cho phép thấp hơn agy, theo điểm phần trăm dạng thập phân.

    Returns:
        Danh sách lý do không đạt. Rỗng khi đạt.
    """
    reasons: list[str] = []
    if candidate["records_rejected"]:
        reasons.append(f"{candidate['records_rejected']} bản ghi vi phạm hợp đồng")
    if candidate["missing_ids"]:
        reasons.append(f"thiếu {candidate['missing_ids']} id")
    for metric in METRICS:
        floor = baseline[metric] - margin
        if candidate[metric] < floor:
            reasons.append(f"{metric} {candidate[metric]:.3f} thấp hơn ngưỡng {floor:.3f}")
    return reasons
