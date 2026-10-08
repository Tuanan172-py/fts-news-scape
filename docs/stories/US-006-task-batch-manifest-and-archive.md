---
id: US-006
type: story
title: Task batch manifest and archive lifecycle management
status: retired
lane: normal
created: 2026-09-07
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
adr: [ADR-0010]
evidence: ["commit:193bfaf", "path:project/src/agent/manifest.py", "path:project/src/agent/archive.py", "test:project/tests/test_batch_manifest.py", "metric:3/3 tests passed, 255/255 suite passed"]
verify: "pytest tests/test_batch_manifest.py"
original: "commit:193bfaf"
reconstructed: 2026-10-06
summary: Task export wrote a batch manifest and printed a summary table, and ingest archived DoD-passing task packets; the L1/Gold export path was retired by ADR-0010.
---

# US-006 — Task batch manifest and archive lifecycle management

## Contract

- Batch task packets for subagents (batches of 20, 50 or 100 articles) were written into one flat folder `data/agent_tasks/`.
- Users and subagents could not tell which article belonged to which batch, had no summary manifest, and old tasks were never archived after ingest.
- After this story, export MUST write `batch_manifest.json` in `data/agent_tasks/` (and `data/agent_tasks/l1/`) and print a summary table on the terminal.
- Ingest MUST move DoD-passing tasks to `data/agent_tasks/archive/<date>/` so the active pool stays clean.

## Acceptance Criteria

- [x] `data/agent_tasks/batch_manifest.json` exists with `batch_id`, `created_at`, `batch_size`, `order` and an `articles` array listing each article in the batch.
- [x] The export command prints a summary table (index, time, source, title).
- [x] When ingest completes (`dod_pass=1`), the matching `.task.json` files move safely into `data/agent_tasks/archive/<date>/`.
- [x] Unit tests cover manifest generation, table printing and archiving, all passing.

## Design Notes

- The original file was Vietnamese and lost several leading characters (`atch_manifest.json`, `rticles`); the field names are restored here from `project/src/agent/manifest.py`.
- Reconstructed: the original story file was lost on disk on 2026-09-07 (see US-008 data-loss incident). `manifest.py` and `archive.py` were recovered from bytecode, and the text came back with commit 193bfaf.
- Known debt recorded in US-008: `archive_completed_tasks` moves only `<article_id>.task.json`; batch packets `batch_XX.task.json` stay forever.
- Retired: ADR-0010 ended the two-tier L1/Gold lane. The manifest callers (`agent_export.py`, `l1_route.py`, `run_agent_hierarchy.py`) no longer run.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `pytest tests/test_batch_manifest.py` | passed, 3/3; full suite 255/255 |
| Integration | CLI `--export` and `--batch-info` with a live table | passed |
| Platform | none | not run |

## Evidence

- `harness.db` story row US-006 (updated 2026-09-07): "Pytest tests/test_batch_manifest.py passed 3/3, 255/255 suite passed, CLI --export and --batch-info verified with live table".
