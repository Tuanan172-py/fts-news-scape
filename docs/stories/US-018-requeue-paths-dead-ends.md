---
id: US-018
type: story
title: Requeue paths for held, failed and claimed dead ends
status: changed
lane: normal
created: 2026-09-17
updated: 2026-10-06
lang: en
authors: [unknown]
adr: [ADR-0010]
plan: []
evidence: [commit:0f1a65c, path:project/scripts/maintenance/requeue.py, path:project/src/morninger.py, test:project/tests/test_state_requeue_paths.py]
verify: "cd project; C:/venvs/news-scape/Scripts/python.exe -m pytest tests/ -q"
reconstructed: 2026-10-06
summary: Every stuck queue state got a controlled path back to pending, so fixing a root cause also rescued old articles; the manual requeue script was later barred by ADR-0010.
---

# US-018 — Requeue paths for held, failed and claimed dead ends

## Contract

- Every stuck state (`held`, `failed`, stale `claimed`) MUST have a controlled path back to `pending` (reconstructed from the harness.db row).
- Fixing a root cause MUST also rescue articles stuck earlier, without manual SQL.
- Changed: the `reclaim_stale` job remains in morninger, but AGENTS.md (ADR-0010) forbids calling `requeue.py`.

## Acceptance Criteria

- [x] `Catalog.enqueue` upserts `held` to `pending` when a later derive succeeds, with an attempt cap.
- [x] `scripts/maintenance/requeue.py` handles `failed` and defaults to dry-run.
- [x] `reclaim_stale` runs as its own scheduler job in morninger.
- [x] `claim()` calls `reclaim_stale` once instead of once per item.
- [x] The radar shows the count for each stuck state.

## Design Notes

- Phase 03 of plan `20260917-1420-pipeline-integrity-remediation`.
- harness.db has no trace row for this story; trace 53 under US-019 covers phases 01 to 04 together.
- `project/src/morninger.py` still schedules `Catalog(...).reclaim_stale()`.
- ADR-0010 ended the L1/Gold lane; AGENTS.md lists `requeue.py` among commands that MUST NOT be called.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python -m pytest tests/test_state_requeue_paths.py -q` | 3 passed (harness.db evidence) |
| Integration | dry-run default of `requeue.py` | verified safe (harness.db evidence) |
| Platform | morninger `reclaim_stale` job and radar dead-end display | active (harness.db evidence) |

## Evidence

- Commit 0f1a65c (2026-09-17), "complete integrity remediation across phases 01-04 (US-011..US-019)".
- harness.db story row US-018; no dedicated trace row.
