---
id: US-025
type: story
title: Article Lane post-W365 hardening of radar and finish
status: implemented
lane: normal
created: 2026-09-23
updated: 2026-10-06
lang: en
authors: [unknown]
adr: [ADR-0010]
plan: []
evidence: [commit:77e166f, path:project/src/db/preflight.py, path:project/scripts/article_run.py, test:project/tests/test_article_lane_hardening.py, wave:W365, metric:514 tests passed]
verify: "python -m pytest tests/ -q"
reconstructed: 2026-10-06
summary: The radar recommends only Article Lane commands, article_run --finish fails loudly on ingest errors or missing articles, readPacket reads object lines, and --where reports the DB path and write access.
---

# US-025 — Article Lane post-W365 hardening of radar and finish

## Contract

- The radar MUST recommend only Article Lane commands (reconstructed from the harness.db row).
- `article_run --finish` MUST exit non-zero when ingest fails, the DB is not writable, or wave coverage is below 90%.
- The conductor `readPacket` MUST read packet `lines[]` objects; `--where` MUST print the DB path and write access.

## Acceptance Criteria

- [x] `pytest tests/` passes 100%.
- [x] `radar status` no longer mentions `l1_entity_matcher` or `gold_financial_analyst`.
- [x] A test proves `--finish` exits non-zero when ingest returns non-zero.
- [x] A test proves the `readPacket` template reads `r.lines`.

## Design Notes

- New module `project/src/db/preflight.py` probes DB write access with a real write, because `BEGIN IMMEDIATE` does not detect a read-only file (trace 74).
- `--finish` verifies coverage against the wave's own article set; `--only` runs selected steps.
- `--repair` no longer repacks articles already patched; `L1Runner` writes `l1_tasks` for `article_lane`.
- `token_ledger --workers-only` separates worker sessions from the conductor session.
- Four follow-ups needing approval were logged as backlog items 25 to 28.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python -m pytest tests/ -q` | 514 passed, 20 new in `test_article_lane_hardening.py` |
| Integration | `readPacket` executed on Node with object `lines[]` | pass |
| Platform | `--finish --only ingest,verify` on wave W365 | L1 330 to 361 of 365 (98.9%), content 364 of 365 |

## Evidence

- Commit 77e166f (2026-09-24), the `--finish` fail-loud, DB write check and `--where` change, tagged US-025.
- harness.db story row US-025 and trace 74, outcome `completed`.
- Workers-only ledger for W365: 7 sessions, 2,850 tokens per article, at most 1 turn.
