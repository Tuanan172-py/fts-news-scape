"""Orchestrate execution of L1 entity recognition."""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from src.agent.l1_classifier import classify_title
from src.core import paths
from src.agent.l1_router import (
    CODE_FIRST_PROVIDER, build_code_first_output, build_l1_task_packet, check_l1_dod,
    route_article, write_l1_packet,
)
from src.core.models import now_vn_iso


class L1Runner:
    """Drive the L1 entity recognition workflow and process its results.

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

    # -- producer: code-first -> l1_tasks + packet -----------------------------
    def route_and_export(self, article: dict, *, review: str = "all") -> dict:
        """Classify entities automatically, store the task and write the work package file.

        Args:
            article: Article data to process.
            review: Package export mode ('all', 'missed' or 'none').

        Returns:
            Classification dict with the work package path when one is written.
        """
        rec = route_article(article, self.reg)
        aid = article.get("article_id")
        emit = False if review == "none" else (review == "all" or (review == "missed" and rec["route"] == "needs_agent"))

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

    # -- producer 2: materialize the DETERMINISTIC result -> l1_outputs ----------
    def ingest_code_first(self, task: dict) -> dict:
        """Materialize an automatic classification as a standard L1 output record.

        Args:
            task: Task record from the l1_tasks table.

        Returns:
            Result dict with the validity status, article identifier and error list.
        """
        aid = task["article_id"]
        title = task.get("title") or ""

        # Prefer articles.title because it is the title the user sees. For 122 of 1320
        # articles (mostly CafeF disclosure pages) the Silver title is the header of the
        # company profile page (`Ngân hàng TMCP Phát triển T.P Hồ Chí Minh (HOSE)`) while the
        # real article is `HDB: Thông báo thay đổi địa điểm...`. Recognition on the wrong
        # title loses the code (HDB matches by code in the real title) and makes `surface`
        # unverifiable in the user deliverable. The root cause is Silver title extraction.
        art = self.store.get_by_hash(aid)
        art_title = (getattr(art, "title", None) or "").strip() if art else ""
        if art_title and art_title != title:
            title = art_title
            task = {**task, "title": title}

        rec = classify_title(title, self.reg)
        rec["article_id"] = aid
        rec["domain"] = task.get("domain")

        if not (rec.get("entity_ids") or []):
            # The new matcher finds nothing, so the earlier match was almost certainly wrong.
            # Do not write recognized=false (it would lock the task at 'done' permanently);
            # return the task to the agent instead.
            self.store.upsert_l1_task({
                "article_id": aid, "domain": task.get("domain"), "title": title,
                "code_first_json": json.dumps(rec, ensure_ascii=False),
                "route": "needs_agent", "packet_path": task.get("packet_path"),
                "enqueued_at": task.get("enqueued_at") or now_vn_iso(),
            })
            return {"ok": False, "article_id": aid, "reason": "no_entity_after_recheck"}

        # Sync the title back into l1_tasks: DoD grounding and the user deliverable must
        # verify against the same title.
        if (task.get("title") or "") != (self.store.get_l1_task(aid) or {}).get("title"):
            self.store.upsert_l1_task({
                "article_id": aid, "domain": task.get("domain"), "title": title,
                "code_first_json": json.dumps(rec, ensure_ascii=False),
                "route": "resolved", "packet_path": task.get("packet_path"),
                "enqueued_at": task.get("enqueued_at") or now_vn_iso(),
            })

        output = build_code_first_output(rec, aid)
        ok, reasons = check_l1_dod(output, title, self.reg)
        self.store.insert_l1_output({
            "article_id": aid,
            "output_json": json.dumps(output, ensure_ascii=False),
            "recognized": 1,
            "agent_provider": CODE_FIRST_PROVIDER,
            "model_used": output["processing_metadata"]["model_used"],
            "confidence": None,          # table lookup: no self-scored confidence
            "dod_pass": 1 if ok else 0,
            "dod_reasons": json.dumps(reasons, ensure_ascii=False),
            "created_at": now_vn_iso(),
            "l1_source": CODE_FIRST_PROVIDER,
        })
        if ok:
            self.store.set_l1_status(aid, "done", done_at=now_vn_iso())
        else:
            self.store.set_l1_status(aid, "failed", error=json.dumps(reasons[:3], ensure_ascii=False))
        return {"ok": ok, "article_id": aid, "dod_pass": ok, "reasons": reasons,
                "entity_ids": rec["entity_ids"]}

    def drain_code_first(self, *, limit: int | None = None, dry_run: bool = False) -> dict:
        """Process all pending automatic classification tasks.

        Args:
            limit: Maximum number of tasks to process.
            dry_run: If True, only count and check without writing to the database.

        Returns:
            Dict with the counts of scanned, written, DoD-failed and rerouted records.
        """
        conn = self.store.connect()
        try:
            sql = ("SELECT * FROM l1_tasks WHERE route = 'resolved' AND status = 'pending' "
                   "ORDER BY enqueued_at DESC")
            if limit:
                sql += f" LIMIT {int(limit)}"
            tasks = [dict(r) for r in conn.execute(sql)]
        finally:
            conn.close()

        stat = {"scanned": len(tasks), "written": 0, "dod_fail": 0, "rerouted": 0}
        if dry_run:
            for t in tasks:
                rec = classify_title(t.get("title") or "", self.reg)
                if not (rec.get("entity_ids") or []):
                    stat["rerouted"] += 1
                    continue
                out = build_code_first_output(rec, t["article_id"])
                ok, _ = check_l1_dod(out, t.get("title") or "", self.reg)
                stat["written" if ok else "dod_fail"] += 1
            return stat
        for t in tasks:
            r = self.ingest_code_first(t)
            if r.get("reason") == "no_entity_after_recheck":
                stat["rerouted"] += 1
            elif r["ok"]:
                stat["written"] += 1
            else:
                stat["dod_fail"] += 1
        logger.info("[l1/code-first] {}", stat)
        return stat

    # -- consumer: agent output -> validate + DoD -> mark -----------------------
    def _register_article_lane_task(self, aid: str) -> dict | None:
        """Write an `l1_tasks` row for an article that came from the Article Lane without L1 routing.

        The Article Lane selects articles from `work_items` and bypasses `l1_route.py`, so
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
