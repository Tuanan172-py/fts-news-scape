---
id: US-024
type: story
title: Radar L1 coverage of articles published today
status: changed
lane: normal
created: 2026-09-17
updated: 2026-10-06
lang: en
authors: [unknown]
adr: [ADR-0010]
plan: []
evidence: [commit:c6c2a56, path:project/scripts/pipeline_radar.py, test:project/tests/test_cli_entrypoints.py, "metric:167/318 articles published today had L1 (52.5%)"]
verify: "historical: no verify command recorded"
reconstructed: 2026-10-06
summary: The radar printed how many articles published today had a passing L1 output, how many waited for an agent and how many were unrouted; US-025 later rewrote the radar for the Article Lane.
---

# US-024 — Radar L1 coverage of articles published today

## Contract

- `pipeline_radar` MUST print, for articles published today, the count with an L1 `dod_pass` output (reconstructed from the harness.db row).
- It MUST also print the count waiting in `needs_agent` and the count not yet routed.
- Changed: the radar still measures coverage by `published_at`, but US-025 rewrote it around Article Lane states after ADR-0010.

## Acceptance Criteria

- [x] The new coverage line appears in `radar status`.
- [x] The radar is listed in `AUTOMATION_CLIS`.
- [x] `py_compile` and pytest pass.

## Design Notes

- Two read-only queries and one print line were added to `project/scripts/pipeline_radar.py` (reconstructed from trace 58).
- The coverage is keyed on `published_at`, so it reports what the reader sees for the day, not what was captured.
- The routing states `needs_agent` and "unrouted" belonged to the L1 lane that ADR-0010 retired.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | none recorded | harness.db `unit_proof=0` |
| Integration | `test_cli_entrypoints` | 11 passed, 1 new for the radar |
| Platform | radar on the operational DB, 2026-09-17 | 167/318 (52.5%), 57 waiting for an agent, 88 unrouted |

## Evidence

- Commit c6c2a56 (2026-09-18) adds the radar lines and the `test_cli_entrypoints.py` entry; no commit message names US-024.
- harness.db story row US-024 and trace 58, outcome `completed`.
