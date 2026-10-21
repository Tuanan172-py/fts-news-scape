"""Orchestrate the end-user delivery flow: compile subscriptions, ingest Agent outputs and publish per-user hand-off files."""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from src.users.compile import (
    DEFAULT_INPUT_ROOT, DEFAULT_OUTPUT_ROOT, compile_all, enabled_users,
)


def union_subscription(registry, users) -> set[str]:
    """Union all entities that the given users subscribed to.

    Args:
        registry: EntityRegistry object that manages the entity catalog.
        users: User names.

    Returns:
        Set of unique entity ids.
    """
    ids: set[str] = set()
    for u in users:
        ids |= registry.resolve_subscription(u)
    return ids


def _ingest_dir(runner_ingest, outputs_dir: str | Path) -> tuple[int, int]:
    """Ingest every JSON output file in a directory through an ingest function.

    Args:
        runner_ingest: Function that ingests one parsed output dict.
        outputs_dir: Directory that holds the JSON output files.

    Returns:
        Tuple of the success count and the failure count.
    """
    ok = fail = 0
    for p in sorted(Path(outputs_dir).glob("*.json")):
        try:
            res = runner_ingest(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
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
        force: bool = False,
        l1_outputs_dir: str | Path | None = None,
        agent_outputs_dir: str | Path | None = None) -> dict:
    """Run the workflow that compiles subscriptions, ingests outputs and publishes per-user news.

    Args:
        input_root: Directory that holds the user subscription files.
        output_root: Directory that stores the hand-off output.
        store: ArticleStore object connected to the database.
        registry: EntityRegistry object that maps entities.
        db_path: Database file path (used when store is None).
        users: Users to process; None selects all enabled users.
        date: Filter by a specific publication date ('YYYY-MM-DD').
        days: Filter by the number of most recent days.
        do_compile: Allow recompiling the Excel/CSV subscription files.
        force: Overwrite published output files even if they already exist.
        l1_outputs_dir: Optional directory with L1 validation outputs to ingest.
        agent_outputs_dir: Optional directory with Gold analysis outputs to ingest.

    Returns:
        Dict with the enabled user list, the published row counts per user and the total.
    """
    from src.agent.entities import load_registry

    # 1. compile input to yaml, then reload the subscription from disk
    if do_compile:
        compile_all(input_root, registry or load_registry())
        reg = load_registry()
    else:
        reg = registry or load_registry()

    # 2. set of enabled users
    enabled = {u.strip() for u in users if u.strip()} if users else enabled_users(input_root)

    # 3. store
    if store is None:
        from src.core.config import load_settings
        from src.db.store import ArticleStore
        store = ArticleStore(db_path=db_path or load_settings()["database"]["path"])

    # 4. ingest submitted outputs, if any; idempotent (the DB returns cached once passed)
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

    # 5. final per-user output (minimum gate is L1; Gold is optional enrichment plus checkpoint)
    from src.export.user_output import UserOutputWriter
    # `enabled` is input-driven and authoritative: an empty set means no users (not None = all).
    writer = UserOutputWriter(store, reg, output_root=output_root, enabled=enabled)
    counts = writer.write(date=date, days=days, force=force)
    total = sum(counts.values())
    logger.info("done workflow: enabled={} users_with_output={} total_rows={}",
                sorted(enabled), len(counts), total)
    return {"enabled": sorted(enabled), "counts": counts, "total": total}
