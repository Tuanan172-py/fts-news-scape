"""Ingest Article Lane entity recognition records through the L1 DoD gate."""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from src.core import paths
from src.agent.l1_router import CODE_FIRST_PROVIDER, check_l1_dod
from src.core.models import now_vn_iso


class L1Runner:
    """Accept entity recognition records and store them after the DoD check.

    Attributes:
        store: Base data store (SQLite or equivalent).
        task_dir: Directory that stores the L1 work packages as JSON files.
        reg: EntityRegistry.
    """

    def __init__(self, store, registry=None, *, task_dir: str | Path | None = None):
        """Initialize the L1Runner.

        Args:
            store: Data store that holds articles and tasks.
            registry: Optional entity registry; None loads it through load_registry().
            task_dir: Directory that stores the L1 work package files.
        """
        self.store = store
        self.task_dir = str(task_dir or paths.agent_tasks_dir() / "l1")
        if registry is None:
            from src.agent.entities import load_registry
            registry = load_registry()
        self.reg = registry

    # -- consumer: agent output -> validate + DoD -> mark -----------------------
    def _register_article_lane_task(self, aid: str) -> dict | None:
        """Write an `l1_tasks` row for an article that came from the Article Lane without L1 routing.

        The Article Lane selects articles from `work_items` and bypasses the retired L1 routing, so
        some articles never had an `l1_tasks` row. Without that row the recognition record
        is rejected with "no l1_task" even when the model answered correctly. The title is
        read from the `articles` table, not from the model output, so the acceptance gate
        still checks against the source.

        Args:
            aid: Article identifier.

        Returns:
            The `l1_tasks` row just written, or None when the article is not in `articles`.
        """
        article = self.store.get_by_hash(aid)
        if article is None:
            return None
        self.store.upsert_l1_task({
            "article_id": aid,
            "domain": article.source_domain,
            "title": article.title or "",
            "code_first_json": None,
            "route": "article_lane",
            "packet_path": None,
            "enqueued_at": now_vn_iso(),
        })
        return self.store.get_l1_task(aid)

    def ingest_output(self, output: dict | str) -> dict:
        """Accept, DoD-check and store an agent result.

        Args:
            output: Result dict, or path of a JSON file that holds the agent analysis.

        Returns:
            Dict with the processing status and the DoD result.
        """
        if isinstance(output, str):
            output = json.loads(Path(output).read_text(encoding="utf-8"))
        aid = output.get("article_id")
        if not aid:
            return {"ok": False, "reason": "missing article_id"}

        task = self.store.get_l1_task(aid) or self._register_article_lane_task(aid)
        if task is None:
            return {"ok": False, "article_id": aid, "reason": "no l1_task"}

        # Idempotent replay: return the cached result when an agent output already passed DoD.
        cached = self.store.get_l1_output(aid)
        if cached and cached.get("dod_pass") and cached.get("l1_source", "agent") != CODE_FIRST_PROVIDER:
            return {"ok": True, "article_id": aid, "cached": True, "dod_pass": True}
        # A code_first record is provisional: an agent may overwrite it, never the reverse.
        # docs/decisions/0003-code-first-l1-delivery.md

        title = task.get("title") or ""
        ok, reasons = check_l1_dod(output, title, self.reg)

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
