# TEST_MATRIX.md — Evidence Vocabulary + Live Proof Table (H2-H5)

Golden rule: **"No proof = not implemented."** A claim without a mechanical result is a plan, not a fact.

> [!TIP]
> **H2-H5 Queryable Matrix:**
> From H2 on, the live status table is stored in `harness.db` and queried in real time with:
> ```powershell
> python scripts/harness_cli.py query matrix
> ```

## Status enum

| Status | Meaning |
|--------|---------|
| `planned` | Story exists, not started. |
| `in_progress` | Being worked (WIP=1 per worktree, ADR-0022). |
| `implemented` | Reached ONLY via a real validation command that ran + is recorded. Never hand-flipped. |
| `changed` | Previously implemented, since modified (needs re-proof). |
| `retired` | Removed / superseded. |
| `blocked` | Halted on an external dependency / Hard Gate / ADR requirement. |
| `deferred` | Intentionally postponed with explicit reason. |

## Proof tiers

| Tier | For news-scape means |
|------|----------------------|
| **Unit** | Pure-function tests (parsers, dedup hash, DoD gate, contract validator) — `pytest tests/<package>/` from `project/`. |
| **Integration** | Scraper → parse → dedup → store against captured fixtures. |
| **E2E** | A full capture cycle (`scripts/run_once.py <domain>`) or a wave that passes `scripts/article_run.py --finish` (coverage gate). |
| **Platform** | Runtime/ops (`ops_daemon`, scheduler, WAL, graceful shutdown, `python -m src.monitor.health`). |

A tier is `1` (passed, evidence recorded), `0` (not passed/not run), or `—` (N/A for this story).

## Proof table snapshot (frozen 2026-09-17)

This hand table is a historical snapshot and is not maintained. The live source is `python scripts/harness_cli.py query matrix`.

| Story | Parent/Epic | Status | Unit | Integ | E2E | Platform | Evidence |
|-------|-------------|--------|:----:|:-----:|:---:|:--------:|----------|
| [US-001](stories/US-001-gold-agent-output-contract.md) | Phase 3 — Gold / agent-extract | `planned` | 0 | — | — | — | Hard gate (blocked on contract decision + ADR) |
| [US-002](stories/US-002-optimize-user-output-format.md) | Per-User Output Workflow | `implemented` | 1 | 1 | — | — | Pytest 13/13 passed + real run 60 rows generated |
| [US-003](stories/US-003-antigravity-multi-agent-hierarchy.md) | Antigravity Multi-Agent Hierarchy | `implemented` | 0 | 0 | — | — | Story exists but has NO proof row — debt from an earlier session |
| US-004 · US-006 · US-007 | Batch processing / manifest / payload optimization | `lost` | — | — | — | — | **Story files lost** in the 2026-09-07 incident (untracked, not recoverable) — see US-008 §6 |
| [US-008](stories/US-008-l1-only-gate-and-backlog-tooling.md) | Per-User Output + Multi-Agent Hierarchy | `implemented` | 1 | 1 | 0 | — | 355 passed · real export of 424 rows (GOLD 384/L1_ONLY 40) · 17 batches for 423 T1 articles · commit `9c06234` |
| [US-011](stories/US-011-bronze-capture-cadence-and-deferred-deleted-article-loss-prevention.md) | Bronze Ingestion Pipeline | `implemented` | 1 | 1 | — | — | 395/395 pytest passed · capture_interval 15→5p · deleted_at_source (404/410) · automatic l1_route job (retired since by ADR-0010) |
| [US-012](stories/US-012-content-recovery-engine.md) | Bronze Ingestion Pipeline | `implemented` | 1 | 1 | — | — | 403/403 passed · fixes US-011 regression (retry persisted to DB) · giveup cap 5 · mode=failed · rejects error-page artifacts |
| [US-013](stories/US-013-radar-false-404-and-bronze-guard-rail.md) | Bronze Ingestion Pipeline | `implemented` | 1 | — | — | — | 403/403 passed · guard rail proven RED/GREEN on znews.yaml · radar warns on false 404 per domain |
| [US-014](stories/US-014-context-budget-counts-orchestrator-reads-only.md) | Harness policy | `implemented` | 1 | — | — | — | CONTEXT_RULES §1 + TRACE_SPEC §3 · backlog #6 resolved · traces #46-48 reach score_context 1.0 |
| [US-015](stories/US-015-production-audit-cli-blind-spot-and-schema-regression.md) | Bronze Ingestion Pipeline | `implemented` | 1 | 1 | 1 | **1** | 413/413 passed · 5 live defects found by real runs · **first platform proof**: morninger `capture/10min` + auto-drain `fetched=14 deleted_at_source=1` |

> Rule reminder: Stories reach `implemented` ONLY after validation commands run and results are recorded. Never hand-flip.

