"""Ingest in-depth agent analysis results through the DoD gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from loguru import logger

from src.agent.dod import check_dod, verify_preconditions
from src.core import paths
from src.core.models import now_vn_iso
from src.handoff.catalog import Catalog


class AgentRunner:
    """Ingest agent analysis results against their work packages.

    Attributes:
        store: Database store.
        catalog: Catalog object that manages the work item catalog.
        task_dir: Directory that stores the JSON work package files.
    """

    def __init__(self, store, *, task_dir: str | Path | None = None):
        """Initialize the AgentRunner.

        Args:
            store: Database store.
            task_dir: Directory that stores work package files; defaults to `paths.agent_tasks_dir()`.
        """
        self.store = store
        self.catalog = Catalog(store)
        self.task_dir = str(task_dir or paths.agent_tasks_dir())

    # -- helpers --------------------------------------------------------------
    @staticmethod
    def _load_work_package(package_path: str) -> dict:
        # Accepts paths relative to the data root, paths with a data/ prefix, and legacy absolute paths.
        return json.loads(paths.resolve_data_path(package_path).read_text(encoding="utf-8"))

    def _work_item_for(self, article_id: str) -> dict | None:
        """Return the most relevant work item record for an article.

        Args:
            article_id: Identity hash of the article.

        Returns:
            Work item record dict, or None if it does not exist.
        """
        conn = self.store.connect()
        try:
            row = conn.execute(
                "SELECT * FROM work_items WHERE article_id=? "
                "ORDER BY CASE status WHEN 'claimed' THEN 0 WHEN 'pending' THEN 1 "
                "ELSE 2 END, id DESC LIMIT 1", (article_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # Work package version of the Article Lane. 1.1 takes the article body from the full
    # Silver text to match the packet and citations (ADR 0018); a 1.0 package holds the RSS
    # excerpt, so Silver citations cannot be verified against it. Old packages are rebuilt
    # on the next ingest.
    WORK_PACKAGE_VERSION = "1.1"

    def _register_article_lane_item(self, article_id: str) -> dict | None:
        """Register the work_item and work_package of an Article Lane article when missing.

        Args:
            article_id: Identity hash of the article.

        Returns:
            The work_item record just registered, or None when the article is not found.
        """
        from src.agent.silver_source import read_silver_text

        article = self.store.get_by_hash(article_id)
        if article is None:
            return None

        silver_text = read_silver_text(getattr(article, "source_domain", None),
                                       getattr(article, "published_at", None),
                                       article_id)
        content = silver_text or article.content_text or article.title or ""
        raw_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()

        wp_dir = paths.work_packages_dir()
        wp_dir.mkdir(parents=True, exist_ok=True)
        wp_file = wp_dir / f"{article_id}.json"

        if not wp_file.exists():
            wp_data = {
                "work_package_version": self.WORK_PACKAGE_VERSION,
                "article_id": article_id,
                "title": article.title or "",
                "domain": article.source_domain or "",
                "published_at": article.published_at or "",
                "cleaned_text": content,
                "text_source": "silver" if silver_text else "rss",
                "raw_sha256": raw_sha256,
                "structure": {
                    "text_quality": "high",
                    "content_length": len(content),
                },
                "change_state": "NEW",
            }
            wp_file.write_text(json.dumps(wp_data, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            try:
                kept = json.loads(wp_file.read_text(encoding="utf-8")) or {}
            except (OSError, ValueError):
                kept = {}
            if kept.get("work_package_version") != self.WORK_PACKAGE_VERSION:
                kept["work_package_version"] = self.WORK_PACKAGE_VERSION
                kept["cleaned_text"] = content
                kept["text_source"] = "silver" if silver_text else "rss"
                kept["raw_sha256"] = raw_sha256
                kept.setdefault("title", article.title or "")
                kept.setdefault("domain", article.source_domain or "")
                kept.setdefault("published_at", article.published_at or "")
                structure = kept.get("structure") or {}
                structure["content_length"] = len(content)
                kept["structure"] = structure
                wp_file.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")

        rel_path = paths.to_data_relative(wp_file)

        conn = self.store.connect()
        try:
            cur = conn.execute("SELECT * FROM work_items WHERE article_id=?", (article_id,))
            row = cur.fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO work_items (article_id, raw_sha256, domain, package_path, "
                    "change_state, status, enqueued_at) VALUES (?, ?, ?, ?, 'NEW', 'claimed', ?)",
                    (article_id, raw_sha256, article.source_domain or "", rel_path, now_vn_iso()),
                )
                conn.commit()
                cur = conn.execute("SELECT * FROM work_items WHERE article_id=?", (article_id,))
                row = cur.fetchone()
            elif row["package_path"] != rel_path or row["raw_sha256"] != raw_sha256:
                conn.execute(
                    "UPDATE work_items SET raw_sha256=?, package_path=? WHERE id=?",
                    (raw_sha256, rel_path, row["id"]),
                )
                conn.commit()
                cur = conn.execute("SELECT * FROM work_items WHERE id=?", (row["id"],))
                row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # -- ingest (agent -> producer) --------------------------------------------
    def ingest_output(self, output: dict | str) -> dict:
        """Accept an agent analysis result, check its quality and update the status.

        Args:
            output: Result dict, or path of a JSON file that follows the agent-output-v1 schema.

        Returns:
            Report dict with the validation status, work item id and error details, if any.
        """
        if isinstance(output, str):
            output = json.loads(Path(output).read_text(encoding="utf-8"))
        article_id = output.get("article_id")
        if not article_id:
            return {"ok": False, "reason": "missing article_id"}

        item = self._work_item_for(article_id) or self._register_article_lane_item(article_id)
        if item is None:
            return {"ok": False, "article_id": article_id, "reason": "no work_item"}
        raw_sha256 = item["raw_sha256"]

        # Idempotent replay: return the cached result when an output already passed DoD.
        cached = self.store.get_agent_output(article_id, raw_sha256)
        if cached and cached.get("dod_pass"):
            return {"ok": True, "article_id": article_id, "cached": True,
                    "dod_pass": True, "work_item_id": item["id"]}

        try:
            wp = self._load_work_package(item["package_path"])
        except (OSError, json.JSONDecodeError) as e:
            return {"ok": False, "article_id": article_id, "reason": f"package_unreadable: {e}"}

        # Rebuild an old package (not yet Article Lane 1.1) as version 1.1 (ADR 0018).
        if wp.get("work_package_version") != self.WORK_PACKAGE_VERSION:
            upgraded = self._register_article_lane_item(article_id)
            if upgraded:
                item = upgraded
                raw_sha256 = item["raw_sha256"]
                try:
                    wp = self._load_work_package(item["package_path"])
                except (OSError, json.JSONDecodeError) as e:
                    return {"ok": False, "article_id": article_id, "reason": f"package_unreadable: {e}"}

        # Preconditions (guardrail) first, then DoD.
        pre_ok, pre_reasons = verify_preconditions(wp)
        dod_ok, dod_reasons = (False, list(pre_reasons)) if not pre_ok else check_dod(output, wp)
        if not pre_ok:
            dod_ok = False

        pm = output.get("processing_metadata") or {}
        agent_provider = pm.get("agent_provider") or "antigravity"
        model_used = pm.get("model_used") or "flash"
        self.store.insert_agent_output({
            "article_id": article_id, "raw_sha256": raw_sha256,
            "work_item_id": item["id"],
            "output_json": json.dumps(output, ensure_ascii=False),
            "agent_provider": agent_provider,
            "model_used": model_used,
            "confidence": output.get("confidence", 0.9),
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
