---
id: US-019
type: story
title: Functional integrity and hygiene fixes for L1 ingest, DoD registry and scheduler lock
status: changed
lane: normal
created: 2026-09-17
updated: 2026-10-06
lang: en
authors: [unknown]
adr: [ADR-0010]
plan: []
evidence: [commit:0f1a65c, path:project/scripts/l1_ingest.py, path:project/src/orchestrator.py, path:scripts/schema/003-intake-types.sql, test:project/tests/test_functional_and_hygiene.py, metric:435 tests passed]
verify: "cd project; C:/venvs/news-scape/Scripts/python.exe -m pytest tests/test_functional_and_hygiene.py -q"
reconstructed: 2026-10-06
summary: L1 ingest gained its missing json import, both L1 DoD paths received the registry, orchestrator --once took the scheduler lock, and l1_route became demand-driven; ADR-0010 later removed l1_route.
---

# US-019 — Functional integrity and hygiene fixes for L1 ingest, DoD registry and scheduler lock

## Contract

- `l1_ingest` MUST import `json` so batch cleanup does not crash (reconstructed from the harness.db row).
- Both L1 DoD paths MUST receive the entity registry; `orchestrator --once` MUST take the scheduler lock.
- `l1_route` moves to a demand-driven model, and the `harness_cli intake` CHECK constraint is fixed.
- Changed: ADR-0010 removed `l1_route`; `l1_ingest.py` remains as a DoD gate inside `article_run --finish`.

## Acceptance Criteria

- [x] Unit tests pass for `l1_ingest` batch cleanup.
- [x] Unit tests pass for DoD registry validation.
- [x] Unit tests pass for the orchestrator scheduler lock.

## Design Notes

- Phase 04 of plan `20260917-1420-pipeline-integrity-remediation`.
- Trace 53 reports phases 01 to 04 together and lists `l1_ingest.py`, `l1_runner.py`, `orchestrator.py`, `morninger.py`, `pipeline_radar.py`, `user_output.py`, `store.py` and migration `003-intake-types.sql`.
- The SQL date filter of `l1_route` was also verified (harness.db evidence).
- US-026 later removed the `l1_route` job from morninger.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python -m pytest tests/test_functional_and_hygiene.py -q` | 4 passed |
| Integration | full suite after phases 01 to 04 | 435 passed (trace 53) |
| Platform | migration 003 applied to harness.db | applied (trace 53) |

## Evidence

- Commit 0f1a65c (2026-09-17), "complete integrity remediation across phases 01-04 (US-011..US-019)".
- harness.db story row US-019 and trace 53, outcome `completed`.
