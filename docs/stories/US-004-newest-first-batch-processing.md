---
id: US-004
type: story
title: Newest-first batch task processing (blocks of 50 to 100 tasks)
status: retired
lane: normal
created: 2026-09-04
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
adr: [ADR-0010]
evidence: ["commit:193bfaf", "test:project/tests/test_handoff.py", "metric:251/251 tests passed including test_catalog_newest_first_order"]
verify: "pytest tests/test_handoff.py"
original: "commit:193bfaf"
reconstructed: 2026-10-06
summary: L1 and Gold task export claimed the newest articles first in bounded batches and skipped finished L1 articles; the L1/Gold lane was retired by ADR-0010.
---

# US-004 — Newest-first batch task processing (blocks of 50 to 100 tasks)

## Contract

- `Catalog.claim()` ordered tasks by `enqueued_at ASC` (oldest first), and `l1_route.py` scanned all historical files in ascending order without a batch limit.
- That dumped 1,600+ tasks at once, overwhelmed subagents and delayed analysis of the freshest financial news.
- After this story, task processing MUST give priority to the newest items (`enqueued_at DESC, id DESC`).
- Batch size MUST be bounded (configurable 20 to 100, default 50), and L1 MUST skip articles already `status='done'`.
- The master orchestrator runner MUST support `--batch-size` and block execution.

## Acceptance Criteria

- [x] AC-1 (catalog newest-first order): `Catalog.claim(worker_id, order="desc")` and `Catalog.list_pending(limit, order="desc")` order by `enqueued_at DESC, id DESC`.
- [x] AC-2 (agent runner export): `AgentRunner.export_tasks()` passes `order` to `Catalog.claim()`.
- [x] AC-3 (agent export CLI): `scripts/agent_export.py` defaults to batch size 50 and order `desc`.
- [x] AC-4 (L1 route ordering and filter): `scripts/l1_route.py` scans newest files first (`reverse=True`), supports `--limit`, and skips articles with `status='done'` in `l1_tasks`.
- [x] AC-5 (orchestrator batch CLI): `scripts/run_agent_hierarchy.py` supports `--batch-size` and passes it to both export scripts.
- [x] AC-6 (tests): all unit and regression tests pass.

## Design Notes

- Reconstructed: the original file left every criterion unchecked. The `harness.db` row (updated 2026-09-04) records `implemented` with unit and integration proof, so the boxes are checked here.
- Reconstructed: the original story file was lost on disk on 2026-09-07 (see US-008 data-loss incident). The current text came back with commit 193bfaf.
- Retired: ADR-0010 ended the two-tier L1/Gold lane. `agent_export.py`, `l1_route.py` and `run_agent_hierarchy.py` no longer run in operation.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `pytest tests/test_handoff.py` | passed; full suite 251/251 including `test_catalog_newest_first_order` |
| Integration | CLI arguments of `agent_export`, `l1_route`, `run_agent_hierarchy` with `--batch-size` and `order=desc` | passed |
| Platform | none | not run |

## Evidence

- `harness.db` story row US-004: "Pytest 251/251 passed including test_catalog_newest_first_order".
- Implementation log in the original file: registered US-004 in `harness.db`.
