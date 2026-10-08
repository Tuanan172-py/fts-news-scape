---
id: US-016
type: story
title: Silver watermark integrity and silver_failures dead-letter table
status: implemented
lane: high-risk
created: 2026-09-17
updated: 2026-10-06
lang: en
authors: [unknown]
adr: [ADR-0007]
plan: []
evidence: [commit:0f1a65c, path:plans/20260917-1420-pipeline-integrity-remediation/plan.md, path:project/src/pipeline/derive.py, test:project/tests/test_silver_watermark_integrity.py, metric:418 tests passed]
verify: "cd project; C:/venvs/news-scape/Scripts/python.exe -m pytest tests/ -q"
reconstructed: 2026-10-06
summary: No Bronze article leaves Silver without a trace; the watermark never passes an unresolved failure, and failures after five attempts move to a dead-letter table shown on the radar.
---

# US-016 — Silver watermark integrity and silver_failures dead-letter table

## Contract

- No Bronze article MAY drop out of Silver derivation without a recorded trace (reconstructed from the harness.db row).
- The Silver watermark MUST NOT advance past an unresolved failure.
- A failure that exceeds five attempts MUST move to dead-letter and appear on the radar with a HIGH warning.

## Acceptance Criteria

- [x] Watermark equals the minimum `fetch_ts` of failures not in dead-letter, or `max(ok_ts)` when clean.
- [x] Table `silver_failures` records `attempts`, `last_error` and `dead_letter`; a later success deletes the row.
- [x] The radar shows the dead-letter count with a HIGH warning.
- [x] A run with `silver_ok=False` and `pkg_ok=True` no longer reports `ok=True`.

## Design Notes

- Decision in ADR-0007; phase 01 of plan `20260917-1420-pipeline-integrity-remediation`.
- Touched `project/src/db/store.py`, `project/src/pipeline/derive.py` and `project/scripts/pipeline_radar.py` (reconstructed from trace 51).
- The derive loop reads each `.meta.json` once per cycle instead of three times.
- A point-in-time backup `monocle_backup_pre_adr0007_260917.db` was taken before the schema change.
- Limitation from trace 51: articles skipped by the old watermark are not recovered automatically; recovery needs `rederive_from_bronze.py`.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python -m pytest tests/ -q` | 418 passed, 5 new; regression test fails on the old code |
| Integration | derive with `silver_failures` on a test DB | pass (harness.db `integration_proof=1`) |
| Platform | morninger restart 2026-09-17 14:55, live derive | "4 processed, 4 ok, 0 failed ... dead_letter=0" |

## Evidence

- Commit 0f1a65c (2026-09-17), "complete integrity remediation across phases 01-04 (US-011..US-019)".
- harness.db story row US-016 and trace 51, outcome `completed`.
