---
id: US-005
type: story
title: Relax export gate to require minimum L1 agent completion
status: retired
lane: normal
created: 2026-09-07
updated: 2026-10-06
lang: en
authors: [unknown]
adr: [ADR-0010]
plan: []
evidence: [commit:193bfaf, path:project/src/export/user_output.py, test:project/tests/test_user_output.py]
verify: "pytest project/tests/test_user_output.py project/tests/test_user_workflow.py -v"
reconstructed: 2026-10-06
summary: The per-user export shipped articles that passed the L1 agent DoD even when Gold output was missing, with empty Gold fields; retired when ADR-0010 ended the L1/Gold lane.
---

# US-005 — Relax export gate to require minimum L1 agent completion

## Contract

- The per-user deliverable export MUST include every article whose L1 agent output has `dod_pass=1`, even when no Gold output exists (reconstructed from the harness.db row).
- Missing Gold fields MUST be written as empty strings instead of dropping the row.
- Retired: ADR-0010 ended the two-tier L1/Gold lane, so this gate no longer describes delivery.

## Acceptance Criteria

- [x] `_GATED_SQL` uses a LEFT JOIN on `agent_outputs`.
- [x] Articles with L1 `dod_pass=1` are routed and exported even when Gold is missing.
- [x] Missing Gold fields default to an empty string.
- [x] Existing and new tests pass.

## Design Notes

- Touched `project/src/export/user_output.py` and `project/tests/test_user_output.py` (reconstructed from harness.db trace 21).
- The change also updated the master audit write in the export module.
- The LEFT JOIN on `agent_outputs` first appears in commit 193bfaf on 2026-09-08; no commit message names US-005.
- ADR-0010 replaced the L1/Gold lane with the Article Lane; Gold fields are no longer a delivery concept.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `pytest project/tests/test_user_output.py project/tests/test_user_workflow.py -v` | pass, 7 items collected (harness.db evidence) |
| Integration | same command, routing test `test_gate_and_routing` | pass (harness.db `integration_proof=1`) |
| Platform | none recorded | not run |

## Evidence

- harness.db story row US-005 and trace 21, outcome `completed`.
- Commit 193bfaf ("version AnPT-FPA", 2026-09-08) introduces `LEFT JOIN agent_outputs` in `user_output.py`.
- ADR-0010 retires the lane this gate belonged to.
