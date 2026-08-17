"""
AgentRunner — khung điều phối Vòng 3, AGENT-AGNOSTIC (không LLM).

2 mặt, tách rời agent thật:
- export_tasks(): claim work_items pending (exactly-once qua Catalog.claim) → dựng
  task-packet → ghi data/agent_tasks/*.task.json. Người dùng đưa packet cho agent
  của họ (prompt tự viết dựa trên schemas/agent-instructions-v1.md).
- ingest_output(): nhận agent-output-v1 (do agent ngoài nộp) → verify preconditions
  → validate schema → check DoD → lưu agent_outputs → mark_done/mark_failed.

Idempotent theo (article_id, raw_sha256): replay trả cached, không double-mark.
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from src.agent.dod import check_dod, verify_preconditions
from src.agent.packet import build_task_packet, write_packet
from src.core.models import now_vn_iso
from src.handoff.catalog import Catalog


class AgentRunner:
    def __init__(self, store, *, task_dir: str = "data/agent_tasks"):
        self.store = store
        self.catalog = Catalog(store)
        self.task_dir = task_dir

    # -- helpers --------------------------------------------------------------
    @staticmethod
    def _load_work_package(package_path: str) -> dict:
        return json.loads(Path(package_path).read_text(encoding="utf-8"))

    def _work_item_for(self, article_id: str) -> dict | None:
        """work_item mới nhất cho article_id (ưu tiên claimed/pending)."""
        conn = self.store.connect()
        try:
            row = conn.execute(
                "SELECT * FROM work_items WHERE article_id=? "
                "ORDER BY CASE status WHEN 'claimed' THEN 0 WHEN 'pending' THEN 1 "
                "ELSE 2 END, id DESC LIMIT 1", (article_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # -- export (producer → agent) --------------------------------------------
    def export_tasks(self, limit: int = 20, *, worker_id: str = "exporter") -> list[dict]:
        """Claim tới `limit` việc pending → ghi task-packet. Trả list {article_id, path}."""
        out: list[dict] = []
        for _ in range(limit):
            item = self.catalog.claim(worker_id)
            if item is None:
                break
            try:
                wp = self._load_work_package(item["package_path"])
            except (OSError, json.JSONDecodeError) as e:
                logger.error("[agent] load package fail {}: {}", item["package_path"], e)
                self.catalog.mark_failed(item["id"], f"package_unreadable: {e}")
                continue
            packet = build_task_packet(wp, work_item_id=item["id"])
            path = write_packet(packet, base_dir=self.task_dir)
            out.append({"article_id": item["article_id"], "work_item_id": item["id"],
                        "path": path})
        logger.info("[agent] exported {} task-packets → {}", len(out), self.task_dir)
        return out

    # -- ingest (agent → producer) --------------------------------------------
    def ingest_output(self, output: dict | str) -> dict:
        """Nhận 1 agent-output-v1. Validate + DoD + persist + mark. Trả summary dict."""
        if isinstance(output, str):
            output = json.loads(Path(output).read_text(encoding="utf-8"))
        article_id = output.get("article_id")
        if not article_id:
            return {"ok": False, "reason": "missing article_id"}

        item = self._work_item_for(article_id)
        if item is None:
            return {"ok": False, "article_id": article_id, "reason": "no work_item"}
        raw_sha256 = item["raw_sha256"]

        # Idempotent replay — đã có output đạt DoD thì trả cached.
        cached = self.store.get_agent_output(article_id, raw_sha256)
        if cached and cached.get("dod_pass"):
            return {"ok": True, "article_id": article_id, "cached": True,
                    "dod_pass": True, "work_item_id": item["id"]}

        try:
            wp = self._load_work_package(item["package_path"])
        except (OSError, json.JSONDecodeError) as e:
            return {"ok": False, "article_id": article_id, "reason": f"package_unreadable: {e}"}

        # Preconditions (guardrail) rồi DoD.
        pre_ok, pre_reasons = verify_preconditions(wp)
        dod_ok, dod_reasons = (False, list(pre_reasons)) if not pre_ok else check_dod(output, wp)
        if not pre_ok:
            dod_ok = False

        pm = output.get("processing_metadata") or {}
        self.store.insert_agent_output({
            "article_id": article_id, "raw_sha256": raw_sha256,
            "work_item_id": item["id"],
            "output_json": json.dumps(output, ensure_ascii=False),
            "agent_provider": pm.get("agent_provider"),
            "model_used": pm.get("model_used"),
            "confidence": output.get("confidence"),
            "dod_pass": 1 if dod_ok else 0,
            "dod_reasons": json.dumps(dod_reasons, ensure_ascii=False),
            "created_at": now_vn_iso(),
        })

        if dod_ok:
            self.catalog.mark_done(item["id"])
        else:
            self.catalog.mark_failed(item["id"], f"dod_fail: {dod_reasons[:3]}")
        logger.info("[agent] ingest {} → dod_pass={} reasons={}",
                    article_id, dod_ok, dod_reasons[:3])
        return {"ok": dod_ok, "article_id": article_id, "work_item_id": item["id"],
                "dod_pass": dod_ok, "reasons": dod_reasons}
