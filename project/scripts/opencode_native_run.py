"""Run the Article Lane directly on an OpenCode session (Muse Spark 1.3 Free)."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.article_contract import CONTRACT_VERSION, validate_record  # noqa: E402
from src.core import paths                             # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = paths.article_packets_dir()
OUT_DIR = paths.agent_outputs_dir("_article")
OPS_DB = paths.data_root() / "ops.db"
VN_TZ = timezone(timedelta(hours=7))

def log_event(wave_id: str, step: str, kind: str, message: str,
              level: str = "info", data: dict | None = None) -> None:
    """Write an operational event to ops.db.

    Args:
        wave_id: Processing wave identifier.
        step: Execution step (analyze/repair/finish).
        kind: Event kind (runner.batch_error/runner.ok).
        message: Short description.
        level: Severity (debug/info/warn/error).
        data: Additional redacted payload.
    """
    OPS_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(OPS_DB), timeout=30)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS ops_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, level TEXT NOT NULL,
          actor TEXT NOT NULL, wave_id TEXT, step TEXT, kind TEXT NOT NULL,
          message TEXT NOT NULL, data_json TEXT)""")
        ts = datetime.now(VN_TZ).isoformat()
        con.execute(
            "INSERT INTO ops_events(ts,level,actor,wave_id,step,kind,message,data_json)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (ts, level, "opencode-native", wave_id, step, kind, message,
             json.dumps(data or {}, ensure_ascii=False)[:4000]))
        con.commit()
    finally:
        con.close()


def append_records(wave: str, batch_id: str, records: list[dict[str, Any]],
                   latency_ms: int = 0, attempt: int = 1) -> dict[str, Any]:
    """Append records to the batch output, validate them and write meta and ops_events.

    Args:
        wave: Wave identifier.
        batch_id: Batch identifier (article_W1001OPC01_01).
        records: New records to append.
        latency_ms: Processing latency in milliseconds.
        attempt: Attempt number.

    Returns:
        Report with added and total counts, status and the output and meta paths.
    """
    task_path = TASK_DIR / f"{batch_id}.task.json"
    task = json.loads(task_path.read_text(encoding="utf-8"))
    items = {a["i"]: a for a in task["a"]}
    out_path = OUT_DIR / f"{batch_id}.output.json"
    meta_path = OUT_DIR / f"{batch_id}.meta.json"
    existing: list[dict[str, Any]] = []
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except ValueError:
            existing = []
    have = {r["i"] for r in existing if isinstance(r, dict) and "i" in r}
    domain_errors: list[dict[str, Any]] = []
    if meta_path.exists():
        try:
            domain_errors = json.loads(meta_path.read_text(encoding="utf-8")).get("domain_errors", [])
        except ValueError:
            domain_errors = []
    added = 0
    transport: dict[str, int] = {}
    for rec in records:
        i = rec.get("i")
        item = items.get(i)
        if item is None:
            domain_errors.append({"article_id": str(i), "batch_id": batch_id,
                                  "attempt": attempt, "ts": datetime.now(VN_TZ).isoformat(),
                                  "provider": "opencode-native",
                                  "model": "muse-spark-1.3-contributor-free",
                                  "class": "schema_fail", "error_redacted": f"i={i} khong thuoc packet"})
            log_event(wave, "analyze", "runner.batch_error", f"{batch_id} i={i} la",
                      level="warn", data={"batch_id": batch_id, "class": "schema_fail"})
            continue
        clean, codes = validate_record(rec, item.get("p") or [], transport, item.get("t") or "")
        err = ",".join(codes)
        if err:
            domain_errors.append({"article_id": str(i), "batch_id": batch_id,
                                  "attempt": attempt, "ts": datetime.now(VN_TZ).isoformat(),
                                  "provider": "opencode-native",
                                  "model": "muse-spark-1.3-contributor-free",
                                  "class": "schema_fail", "error_redacted": err})
            log_event(wave, "analyze", "runner.batch_error", f"{batch_id} i={i}: {err}",
                      level="warn", data={"batch_id": batch_id, "class": "schema_fail"})
            continue
        if i in have:
            continue
        existing.append(clean)
        have.add(i)
        added += 1
    existing.sort(key=lambda r: r["i"])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(existing, ensure_ascii=False, indent=1), encoding="utf-8")
    status = "OK" if len(existing) >= len(items) else "PARTIAL"
    meta = {"batch_id": batch_id, "created_at": datetime.now(timezone.utc).isoformat(),
            "agent_provider": "opencode-native",
            "model_used": "muse-spark-1.3-contributor-free",
            "items_total": len(items), "items_valid": len(existing), "status": status,
            "usage": {"note": "free-tier, token ghi nhan o token_ledger khi finish"},
            "latency_ms": latency_ms, "domain_errors": domain_errors,
            "contract_version": CONTRACT_VERSION, "transport": transport}
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    log_event(wave, "analyze", "runner.ok" if status == "OK" else "runner.partial",
              f"{batch_id}: +{added}, tong {len(existing)}/{len(items)}",
              data={"batch_id": batch_id, "added": added, "total": len(existing)})
    return {"batch_id": batch_id, "added": added, "total": len(existing),
            "expected": len(items), "status": status,
            "out": str(out_path), "meta": str(meta_path)}


def wave_status(wave: str) -> dict[str, Any]:
    """Summarize wave progress from the existing outputs.

    Args:
        wave: Wave identifier.

    Returns:
        Total article count and per-batch expected and present counts.
    """
    manifest = json.loads((TASK_DIR / f"wave_{wave}.json").read_text(encoding="utf-8"))
    rows = []
    total = 0
    for b in manifest["batches"]:
        bid = b["batch_id"]
        out = OUT_DIR / f"{bid}.output.json"
        n = 0
        if out.exists():
            try:
                n = len(json.loads(out.read_text(encoding="utf-8")))
            except ValueError:
                n = 0
        rows.append({"batch_id": bid, "expected": b["n"], "have": n})
        total += n
    return {"wave": wave, "total": total, "expected": manifest["articles"], "batches": rows}
