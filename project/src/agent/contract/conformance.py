"""Score a provider against the gold set and the measured agy baseline (ADR 0017 D7)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agent.contract.article_contract import parse_and_validate

MARGIN = 0.05
METRICS = ("agree_sn", "agree_ts", "tic_f1")


def _load(path: Path) -> Any:
    """Read a UTF-8 JSON file.

    Args:
        path: File path.

    Returns:
        Parsed JSON object.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def score_outputs(output_dir: Path, task_dir: Path, gold: dict[str, dict],
                  batch_ids: list[str]) -> dict[str, Any]:
    """Score the raw output of batches against the gold set.

    Args:
        output_dir: Directory that holds `<batch>.output.json`.
        task_dir: Directory that holds `<batch>.task.json` and `<batch>.map.json`.
        gold: Gold set keyed by `article_id`; values carry `sn`, `ts` and `tic`.
        batch_ids: Identifiers of the batches to score.

    Returns:
        Metrics dict: raw record count, rejected count, missing ids, agreement on `sn`
        and `ts`, F1 of the TIC set, and the number of gold articles scored.
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
    """Compare candidate provider metrics with the recorded agy baseline.

    A candidate passes when no record is rejected, no id is missing, and every
    agreement metric is at least the agy value minus `margin`.

    Args:
        candidate: Metrics of the candidate provider.
        baseline: agy metrics on the same gold set.
        margin: Allowed shortfall below agy, as a decimal fraction.

    Returns:
        Reasons for failure. Empty when the candidate passes.
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
