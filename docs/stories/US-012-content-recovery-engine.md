---
id: US-012
type: story
title: Content recovery engine with stateful retry, give-up cap and transient-failure recovery
status: implemented
lane: normal
created: 2026-09-17
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
adr: []
related: [US-011]
evidence: ["commit:0f1a65c", "path:project/scripts/maintenance/backfill_deferred.py", "test:project/tests/test_backfill_deferred.py", "metric:403 tests passed (from 395, plus 8)"]
verify: "cd project; C:/venvs/news-scape/Scripts/python.exe -m pytest tests/ -q"
original: "commit:0f1a65c"
summary: Every article without full content is retried with a recorded, bounded attempt count; 404/410 and exhausted articles leave the queue, ending the infinite refetch loop US-011 introduced.
---

# US-012 — Content recovery engine with stateful retry, give-up cap and transient-failure recovery

## Contract

- Every article without full content MUST be retried with a bound and a record.
- An article confirmed lost for good (source deleted with 404/410) or retried up to the cap MUST leave the queue.
- No article may be refetched forever.

## Acceptance Criteria

- [x] `_record_attempt()` writes `capture_retry.{attempts,last_at,last_status}` into `metadata_json` on every failure branch (HTTP error, missing file, empty extraction).
- [x] 404/410 sets `source_deleted: true`; reaching `max_attempts` sets `capture_giveup: true`.
- [x] A shared `_EXCLUDE_DEAD` removes both flags from `_DEFERRED_WHERE` and `_FAILED_WHERE`.
- [x] `--mode {deferred,failed,all}` defaults to `deferred` (keeps the runbook and old tests); `morninger` calls `--mode all`.
- [x] `--max-attempts` (5) and `--retry-window-hours` exist; `morninger` passes 24, the CLI default 0 means no limit for manual bulk backfill.
- [x] `SourceBackoff.before_fetch/observe` wraps every fetch on the backfill path.
- [x] `--dry-run` records no retry.
- [x] Early exit when no row exists, so no `HTTPClient` or `RobotsGate` is built for nothing.
- [x] An error-page artifact is never used as article content (found by a test, see Design Notes).

## Design Notes

- Regression fixed: US-011 excluded `source_deleted` articles from `_DEFERRED_WHERE`, but nothing wrote that flag on the backfill path.
- `backfill_deferred.py:244-246` on failure only did `stats["failed"] += 1` and `continue`, never touching the DB.
- Root cause: `_INSERT_SQL` of ArticleStore is `INSERT OR IGNORE` (`project/src/db/store.py:78-81`), so an existing row never updates itself. An explicit `UPDATE` is required.
- Without the fix, after a `morninger` restart each permanently deleted article would be refetched every 5 minutes: about 288 junk requests per article per day, forever.
- Second bug, found by a test: `test_transient_failure_gives_up_after_max_attempts` first failed for an unexpected reason.
- `RawStore.save()` still writes the body on HTTP errors (`raw_store.py`, comment "partial body still saved for inspection"), so a 500 page also produces an `.html` file.
- The next backfill found that file through `_find_bronze()`, extracted the error-page text as `content_text` and marked it `backfilled_from_bronze`. Article content was replaced by the error page.
- The behavior predated US-011, but manual backfill rarely ran. At every 5 minutes it became a data-corruption path.
- Fix: `_find_bronze()` reads the `.meta.json` sidecar and accepts only `capture_status` of `ok` or `partial`. A missing sidecar is still accepted (old or hand-placed artifacts).
- `SourceBackoff` reacts only to 429/503, caps at 16s and keeps in-memory state, so it protects only within one run.
- The real cross-run brake is the attempt cap; backoff is courtesy to the source. The base pace of 3s per domain already comes from `HTTPClient`.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `cd project; C:/venvs/news-scape/Scripts/python.exe -m pytest tests/ -q` | passed, 403 (from 395, plus 8 tests) |
| Integration | same command; backfill runs through fake HTTP and real Bronze files on disk | passed |
| E2E | real network | not run in the session |
| Platform | `morninger` restart | pending at the time; see US-011 and US-015 |

## Evidence

```
403 passed, 550 warnings in 120.96s (0:02:00)
```

- `test_retry_404_marks_source_deleted_and_stops_requerying`: `fake.calls == 1` after two runs; the second run made no network call because the row had left the queue.
- `test_transient_failure_gives_up_after_max_attempts`: `fake.calls == 3` with `max_attempts=3`, although `main()` ran 6 times.
- `test_find_bronze_rejects_error_page_artifact`: `deleted_at_source` and `failed` artifacts are rejected.
- Also: `test_mode_failed_recovers_transient_failure_from_bronze`, `test_backoff_wraps_every_fetch`, `test_dry_run_records_no_attempt` (from the `harness.db` row).
- Trace #46: `score_trace = 1.0`, `score_context = 1.0`. Outcome: completed. No new backlog item.
- Commit f8f4321 also carries the tag US-012 but belongs to a different story (Gold output schema v2-lean); the id was reused.
