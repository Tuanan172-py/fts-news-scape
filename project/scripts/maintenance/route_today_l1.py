"""Script chay dinh tuyen L1 va xuat mini-batches cho ngay 2026-09-15."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.agent.batch_handoff import split_l1_tasks_into_batches
from src.agent.entities import load_registry
from src.agent.l1_runner import L1Runner
from src.agent.manifest import create_batch_manifest, print_batch_summary_table
from src.core.config import load_settings
from src.core.stdio import force_utf8_stdio
from src.db.store import ArticleStore

force_utf8_stdio()

def run_route():
    db_path = load_settings().get("database", {}).get("path", "C:/data/news-scape/monocle.db")
    store = ArticleStore(db_path=db_path)
    reg = load_registry()
    runner = L1Runner(store, registry=reg)

    conn = store.connect()
    try:
        rows = conn.execute("""
            SELECT a.url_title_hash AS article_id, a.title, a.source_domain AS domain, a.published_at
            FROM articles a
            WHERE date(a.published_at) = '2026-09-15'
            AND NOT EXISTS (SELECT 1 FROM l1_tasks lt WHERE lt.article_id = a.url_title_hash)
        """).fetchall()
    finally:
        conn.close()

    print(f"Routing {len(rows)} articles for 2026-09-15...")
    resolved_cnt = 0
    needs_agent_cnt = 0
    exported = []

    for r in rows:
        art = dict(r)
        rec = runner.route_and_export(art, review="missed")
        if rec["route"] == "resolved":
            resolved_cnt += 1
        else:
            needs_agent_cnt += 1
            if rec.get("packet_path"):
                exported.append({
                    "article_id": art["article_id"],
                    "title": rec.get("title") or art["title"],
                    "domain": art["domain"],
                    "time": art["published_at"],
                    "path": rec["packet_path"],
                    "code_first": {
                        "route": rec.get("route"),
                        "relevance": rec.get("relevance"),
                        "entity_ids": rec.get("entity_ids", []),
                        "industries": rec.get("industries", []),
                    },
                })

    print(f"Done routing: resolved={resolved_cnt}, needs_agent={needs_agent_cnt}")

    if exported:
        manifest = create_batch_manifest(exported, runner.task_dir, batch_type="l1", order="desc")
        print_batch_summary_table(manifest)
        batches = split_l1_tasks_into_batches(exported, batch_size=25, base_dir=runner.task_dir)
        print(f"Packed {len(batches)} mini-batches into {runner.task_dir}")

if __name__ == "__main__":
    run_route()
