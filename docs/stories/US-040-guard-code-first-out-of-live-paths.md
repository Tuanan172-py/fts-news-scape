---
id: US-040
type: story
title: Guard code_first out of every live path
status: implemented
lane: normal
created: 2026-10-06
updated: 2026-10-06
lang: en
authors: [claude]
branch: fix/us040-code-first-guard
adr: [ADR-0010]
plan: []
evidence:
  - "commit:072eb8f"
  - "test:project/tests/test_code_first_guard.py"
  - "metric:l1_outputs code_first rows = 3069, all dod_pass=1, created 2026-09-09..2026-09-17"
  - "metric:2570 distinct code_first articles found in the Watchlist sheet of 490 of 580 user xlsx files"
  - "metric:3059 code_first rows in 156 _master/*_L1.csv files"
  - "operator:2026-10-06 confirmed code_first reaching delivery is a bug"
verify: "python -m pytest tests/test_code_first_guard.py -q"
summary: Code-first L1 rows never reach delivery, insight signals, selectors, counts, packet cleanup or Parquet exports.
---

# US-040 — Guard code_first out of every live path

## Contract

- Every live read of `l1_outputs` MUST exclude rows with `l1_source = 'code_first'` (ADR-0010.D4).
- Delivery (`users_output/<user>/<date>.xlsx` and `_master/*.csv`) MUST NOT contain an article whose only L1 result is code-first.
- Counts, selectors, wave coverage, packet cleanup and the `mentions` Parquet export MUST treat a code-first row as "not analysed".
- One shared SQL helper defines the predicate; call sites MUST NOT restate it.

## Acceptance Criteria

- [x] `UserOutputWriter.gated_rows` and `write` return only model-analysed articles.
- [x] `signals.load_data`, `article_pack.load_candidates`, `article_tick.count_pending_articles` and `Catalog.claim(require_l1=True)` ignore code-first rows.
- [x] `article_run.coverage_of` counts a code-first-only article as missing, so `--repair` repacks it.
- [x] `DailyReporter`, `l1_backlog.collect` and `clean_completed_packets._is_done` exclude code-first rows.
- [x] The publisher `mentions` Parquet export drops code-first rows.
- [x] Regression tests on a temporary SQLite DB cover each fixed path.

## Design Notes

- Shared helpers live in `project/src/agent/article_contract.py`: `CODE_FIRST_SOURCE`, `analyzed_l1_sql(alias)`, `not_code_first_sql(alias)` and `not_code_first_sql_for(conn, alias)`.
- `not_code_first_sql_for` checks the real schema. A read-only connection to a legacy DB without `l1_source` gets a constant-true predicate, since such a DB cannot hold code-first rows.
- Fixed live paths: `src/export/user_output.py` (`_GATED_SQL`, the reported leak), `src/export/publisher.py`, `src/monitor/daily_reporter.py`, `src/handoff/catalog.py`, `src/agent/runner.py`, `scripts/article_run.py`, `scripts/l1_backlog.py`, `scripts/maintenance/clean_completed_packets.py`.
- Already guarded, now on the shared helper: `scripts/article_pack.py` (`ANALYZED_L1`, reused by `pipeline_radar.py` and `handoff.py`), `scripts/article_tick.py`, `src/analytics/signals.py`, `src/pipeline/inherit.py`.
- Left unchanged on purpose: `scripts/db_status.py` (provenance breakdown by provider), `scripts/maintenance/heal_orphans.py` (rebuilds article rows, counts nothing), the review DB copy in the publisher (full audit mirror).
- Retired by ADR-0010 and not touched: `l1_route.py`, `agent_export.py`, `auto_pilot.py`, `run_agent_hierarchy.py`, `l1_ingest.py --code-first` and `src/agent/l1_runner.drain_code_first`.
- Delivered files already on disk are not rewritten by this story. Regenerating past deliveries is an operator decision.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python -m pytest tests/test_code_first_guard.py -q` | pass, 12 tests |
| Integration | pytest over 17 test files for the touched modules (full suite not run: it writes the operational DB) | 235 pass, 1 fail pre-existing on base `e4abeb4` (`test_inherit.py::test_refresh_end_to_end_clusters_then_inherits`) |
| Platform | read-only `sqlite3` on `C:\data\news-scape\monocle.db` (`mode=ro`) | 3069 code-first rows measured |

## Evidence

- `commit:072eb8f` carries the guard and the regression tests.
- Before the fix, 154 code-first articles also had a passing Gold output, so they were delivered as "Full" rows.
- The other code-first articles were delivered as "Preliminary" rows, with entities taken from the deterministic lookup.
