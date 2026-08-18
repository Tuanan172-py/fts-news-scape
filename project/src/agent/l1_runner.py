"""
L1Runner — khung điều phối LỚP 1 nhận diện thực thể, AGENT-AGNOSTIC (không LLM).
Mirror AgentRunner (Vòng 3) cho task title-only. 2 mặt tách rời agent thật:

- route_and_export(): với mỗi article → code-first (l1_classifier) → lưu l1_tasks →
  ghi task-packet data/agent_tasks/l1/<id>.task.json cho agent tra soát.
    review='all'    : phát packet cho MỌI tin (agent có quyền tra soát cả tin đã resolved).
    review='missed' : chỉ phát packet cho tin code-first KHÔNG khớp (needs_agent).
- ingest_output(): nhận l1-entity-output-v1 (agent nộp) → validate + check_l1_dod →
  lưu l1_outputs → set_l1_status done/failed. Idempotent theo article_id.

Đầu vào article: silver dict hoặc work-package (đều có title/structure/cleaned_text).
"""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from src.agent.l1_router import (
    build_l1_task_packet, check_l1_dod, route_article, write_l1_packet,
)
from src.core.models import now_vn_iso


class L1Runner:
    def __init__(self, store, registry=None, *, task_dir: str = "data/agent_tasks/l1"):
        self.store = store
        self.task_dir = task_dir
        if registry is None:
            from src.agent.entities import load_registry
            registry = load_registry()
        self.reg = registry

    # -- producer: code-first → l1_tasks + packet -----------------------------
    def route_and_export(self, article: dict, *, review: str = "all") -> dict:
        """Code-first 1 article; lưu l1_tasks; phát packet theo `review`. Trả record."""
        rec = route_article(article, self.reg)
        aid = article.get("article_id")
        emit = review == "all" or (review == "missed" and rec["route"] == "needs_agent")

        packet_path = None
        if emit:
            packet = build_l1_task_packet(article, rec)
            packet_path = write_l1_packet(packet, base_dir=self.task_dir)

        self.store.upsert_l1_task({
            "article_id": aid,
            "domain": article.get("domain"),
            "title": rec["title"],
            "code_first_json": json.dumps(rec, ensure_ascii=False),
            "route": rec["route"],
            "packet_path": packet_path,
            "enqueued_at": now_vn_iso(),
        })
        rec["packet_path"] = packet_path
        return rec

    # -- consumer: agent output → validate + DoD → mark -----------------------
    def ingest_output(self, output: dict | str) -> dict:
        """Nhận 1 l1-entity-output-v1. Validate + DoD + persist + set status."""
        if isinstance(output, str):
            output = json.loads(Path(output).read_text(encoding="utf-8"))
        aid = output.get("article_id")
        if not aid:
            return {"ok": False, "reason": "missing article_id"}

        task = self.store.get_l1_task(aid)
        if task is None:
            return {"ok": False, "article_id": aid, "reason": "no l1_task"}

        # Idempotent replay — đã có output đạt DoD thì trả cached.
        cached = self.store.get_l1_output(aid)
        if cached and cached.get("dod_pass"):
            return {"ok": True, "article_id": aid, "cached": True, "dod_pass": True}

        title = task.get("title") or ""
        ok, reasons = check_l1_dod(output, title)

        pm = output.get("processing_metadata") or {}
        self.store.insert_l1_output({
            "article_id": aid,
            "output_json": json.dumps(output, ensure_ascii=False),
            "recognized": 1 if output.get("recognized") else 0,
            "agent_provider": pm.get("agent_provider"),
            "model_used": pm.get("model_used"),
            "confidence": output.get("confidence"),
            "dod_pass": 1 if ok else 0,
            "dod_reasons": json.dumps(reasons, ensure_ascii=False),
            "created_at": now_vn_iso(),
        })
        if ok:
            self.store.set_l1_status(aid, "done", done_at=now_vn_iso())
        else:
            self.store.set_l1_status(aid, "failed", error=json.dumps(reasons[:3], ensure_ascii=False))
        logger.info("[l1] ingest {} → dod_pass={} reasons={}", aid, ok, reasons[:3])
        return {"ok": ok, "article_id": aid, "dod_pass": ok, "reasons": reasons}
