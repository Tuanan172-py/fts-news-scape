---
id: US-041
type: story
title: Green test suite, per-provider token ledger, and collection coverage analysis
status: implemented
lane: normal
created: 2026-10-08
updated: 2026-10-08
lang: en
authors: [An Pham Thanh, claude-opus-5-5]
related: [US-038]
evidence:
  - test:tests/test_inherit.py
  - test:tests/test_ledger_openrouter.py
  - commit:ac9f22f
verify: manual
summary: Date-independent test suite, accurate per-provider token ledger accounting, and collection coverage analysis.
---

# US-041 — Green test suite, per-provider token ledger, and collection coverage analysis

- **Status:** implemented
- **Lane:** normal
- **Parent / Epic:** Unblock post-migration (US-038)
- **Intake date:** 2026-10-08
- **Depends On:** US-038 (`dev/us038`)

## Contract

Full regression test suite runs green independently of the calendar execution date. Token ledger correctly attributes cost and token metrics to each individual provider when a wave mixes multiple providers. Operators can audit missing collection coverage and identify actions to resume operations.

## Acceptance Criteria

- [x] `test_inherit` no longer depends on calendar execution date: `cluster_job.refresh` accepts fixed date.
- [x] Token ledger calculates metadata per `agent_provider`; mixed waves record two separate rows.
- [x] Cached tokens read from prompt details are accounted in `hit_tokens` and not added to `miss_tokens`.
- [x] `opencode-native` recognized; metadata without token counts recorded with `usage=not recorded`.
- [x] Running `--finish` replaces all stale runner rows for a wave, even when switching providers.
- [x] `--finish` passes `--source auto` when runner source is unknown.
- [x] Collection coverage gap analysis and backlog drainage command recorded in OPEN-ITEMS CAP-1.
- [ ] Opencode adapter records actual usage in metadata (out of scope).

## Design Notes

- E1 duplicate patch batch was fixed prior to this story with claimed set in `cmd_repair`.
- Compensatory crawling limit in morninger cycle is kept under 7 minutes to prevent overlap.
- Developed on dedicated worktree `C:\src\news-scape-us041` on branch `fix/us041-unblock-tests-ledger` off `dev/us038`.

## Verification

| Tier | Command | Status | Evidence |
|---|---|---|---|
| Unit | `python -m pytest tests/test_inherit.py tests/test_ledger_openrouter.py -q` | pass | 2026-10-08 |
| Full | `python -m pytest tests/ -q` | pass | 892 passed, 0 failed |

## Evidence

- Unit tests `tests/test_inherit.py` and `tests/test_ledger_openrouter.py` pass cleanly.
- Full test suite passed with 892 passed tests on 2026-10-08.
