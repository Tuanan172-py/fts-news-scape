"""
user_workflow.py — Orchestrator end-to-end lớp NGƯỜI DÙNG (idempotent, resume theo article_id).

Nối: compile input (xlsx→yaml) → (tùy chọn) nạp output L1/agent đã có → ghi output cuối per user.
Scrape TÁCH khỏi đây (giả định cron/pipeline đã chạy) — xem scripts/run_once.py.
Handoff agent là BẤT ĐỒNG BỘ: phát packet (l1_route.py / agent_export.py) và nạp (ingest) là 2 pha
riêng; workflow này lo pha compile + ingest + output.

Không notify — chỉ log "done".

Ai chạy tay / framework tự động / điểm cần prompt agent / cách cắm cron cho full-auto:
xem docs/design/13-per-user-output-workflow.md §14 (Vận hành & Automate).
"""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from src.users.compile import (
    DEFAULT_INPUT_ROOT, DEFAULT_OUTPUT_ROOT, compile_all, enabled_users,
)


def union_subscription(registry, users) -> set[str]:
    """Hợp mọi entity mà tập user đăng ký — dùng để GIỚI HẠN agent-export (tiết kiệm)."""
    ids: set[str] = set()
    for u in users:
        ids |= registry.resolve_subscription(u)
    return ids


def _ingest_dir(runner_ingest, outputs_dir: str | Path) -> tuple[int, int]:
    ok = fail = 0
    for p in sorted(Path(outputs_dir).glob("*.json")):
        try:
            res = runner_ingest(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001 — 1 file hỏng không chặn cả lô
            logger.warning("ingest fail {}: {}", p.name, e)
            fail += 1
            continue
        ok += 1 if res.get("dod_pass") or res.get("cached") else 0
        fail += 0 if res.get("dod_pass") or res.get("cached") else 1
    return ok, fail


def run(*, input_root: str | Path = DEFAULT_INPUT_ROOT,
        output_root: str | Path = DEFAULT_OUTPUT_ROOT,
        store=None, registry=None, db_path: str | None = None,
        users: list[str] | None = None, date: str | None = None, days: int | None = None,
        do_compile: bool = True,
        l1_outputs_dir: str | Path | None = None,
        agent_outputs_dir: str | Path | None = None) -> dict:
    """Chạy compile → ingest (tùy chọn) → output. Trả {enabled, counts, total}."""
    from src.agent.entities import load_registry

    # 1. compile input → yaml, rồi reload subscription từ disk
    if do_compile:
        compile_all(input_root, registry or load_registry())
        reg = load_registry()
    else:
        reg = registry or load_registry()

    # 2. tập user BẬT
    enabled = {u.strip() for u in users if u.strip()} if users else enabled_users(input_root)

    # 3. store
    if store is None:
        from src.core.config import load_settings
        from src.db.store import ArticleStore
        store = ArticleStore(db_path=db_path or load_settings().get("database", {}).get("path", "data/monocle.db"))

    # 4. ingest output đã nộp (nếu có) — idempotent (DB trả cached khi đã đạt)
    if l1_outputs_dir:
        from src.agent.l1_runner import L1Runner
        r = L1Runner(store, reg)
        ok, fail = _ingest_dir(r.ingest_output, l1_outputs_dir)
        logger.info("L1 ingest: ok={} fail={}", ok, fail)
    if agent_outputs_dir:
        from src.agent.runner import AgentRunner
        a = AgentRunner(store)
        ok, fail = _ingest_dir(a.ingest_output, agent_outputs_dir)
        logger.info("agent ingest: ok={} fail={}", ok, fail)

    # 5. output cuối per user (gate đủ 2 layer + checkpoint)
    from src.export.user_output import UserOutputWriter
    # enabled là input-driven & authoritative: tập rỗng = KHÔNG user nào (đừng đổi thành None=all).
    writer = UserOutputWriter(store, reg, output_root=output_root, enabled=enabled)
    counts = writer.write(date=date, days=days)
    total = sum(counts.values())
    logger.info("done workflow: enabled={} users_with_output={} total_rows={}",
                sorted(enabled), len(counts), total)
    return {"enabled": sorted(enabled), "counts": counts, "total": total}
