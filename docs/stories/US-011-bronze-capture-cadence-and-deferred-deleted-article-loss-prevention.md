---
id: US-011
type: story
title: Bronze capture cadence and deferred or deleted article loss prevention
status: changed
lane: normal
created: 2026-09-17
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
adr: [ADR-0010]
related: [US-012, US-013, US-015]
evidence: ["commit:0f1a65c", "path:project/src/morninger.py", "path:project/scripts/maintenance/backfill_deferred.py", "test:project/tests/test_backfill_deferred.py", "test:project/tests/test_raw_store.py", "metric:395 tests passed, 0 failed"]
verify: "cd project; C:/venvs/news-scape/Scripts/python.exe -m pytest tests/ -q"
original: "commit:0f1a65c"
reconstructed: 2026-10-06
summary: Bronze capture runs faster with automatic deferred backfill and a deleted-at-source flag for 404 and 410; US-015 later changed the interval and ADR-0010 removed the l1_route job.
---

# US-011 — Bronze capture cadence and deferred or deleted article loss prevention

## Contract

- The Bronze cycle MUST detect and store new articles fast enough, with an automatic safety net.
- Some Vietnamese sources remove articles very soon after publishing; this MUST NOT cause permanent loss of full content.
- Silver to L1 (the code-first branch, 0 tokens) MUST be routed automatically, without a human running it or Gold quota.
- Gold stays a separate quota bottleneck, out of scope here.

## Acceptance Criteria

- [x] `capture_interval_minutes` falls from 15 to 5 minutes (`project/config/settings.yaml`).
- [x] `backfill_deferred.py` runs right after each capture cycle (`Morninger.run_capture` then `run_backfill_deferred`), with no operator action.
- [x] HTTP 404 or 410 on a detail page sets `capture_status=deleted_at_source` and `article.metadata.source_deleted=True`, distinct from a transient `failed`.
- [x] `backfill_deferred.py` excludes `source_deleted=True` articles from `_DEFERRED_WHERE`, so a confirmed missing URL is not retried in vain.
- [x] `pipeline_radar.py status` shows how many articles the source deleted before content was captured.
- [x] Job `l1_route` (code-first, `--from-db --date today --mini-batch 25`, 0 LLM tokens) runs on its own schedule (`l1_route_interval_minutes`, default 15) in `morninger.build_scheduler`.
- [x] That job is fully separate from the AutoPilot and Gold quota.
- [x] `build_scheduler()` stays backward compatible: `l1_route_fn` defaults to `None`, so the old 4-argument call registers no job.
- [x] All unit tests pass with no regression.

## Design Notes

- Smallest needed scope: no change to the Bronze, Silver, Gold architecture. It patches three gaps found in audit.
- Audited files: `project/src/orchestrator.py`, `project/src/morninger.py`, `project/src/scrapers/rss_generic.py`, `project/src/scrapers/capture_mixin.py`.
- Gap 1: `max_details_per_cycle` (default 30 to 40 per domain) marks overflow articles `detail_deferred=True`. They were backfilled only by a MANUAL run of `scripts/maintenance/backfill_deferred.py`.
- The window between deferral and the manual backfill is when a Vietnamese source may delete the article. Fix: chain `run_backfill_deferred` right after each capture cycle.
- Gap 2: `raw_store.py` and `capture_mixin.py` did not separate 404/410 from transient errors. The "publish then delete" rate was unmeasurable, and backfill wasted retries. Fix: a `deleted_at_source` branch.
- Gap 3: `l1_route.py` had no schedule; it ran only when a human saw a `pipeline_radar` warning. Fix: its own scheduler job, independent of AutoPilot and Gold.
- Out of scope: domains with `method: rss` (no Bronze raw capture) were NOT moved to `rss_capture`.
- Every currently enabled domain already uses a `CaptureMixin` scraper: cafef, vietstock, vietnambiz, tnck, fireant, baodautu, vneconomy, thoibaotaichinhvietnam.
- The remaining domains have been `enabled: false` since 2026-08-03. Migrating them needs per-site CSS selector checks before anyone re-enables one.
- Changed: US-012 fixed a regression here (nothing wrote `source_deleted` on the backfill path).
- Changed: US-015 fixed further regressions and raised `capture_interval_minutes` from 5 to 10.
- Changed: ADR-0010 removed the `l1_route` job of `morninger` together with the two-tier L1/Gold lane. The Bronze parts remain in force.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `cd project; C:/venvs/news-scape/Scripts/python.exe -m pytest tests/ -q` | passed, 395, 0 failed (only an unrelated `feedparser` DeprecationWarning) |
| Integration | same command; `test_cafef_capture.py` and `test_backfill_deferred.py` run the real scraper and backfill with HTTP fixtures | passed |
| E2E | `run_once.py` live | not run; no real network calls in an audit session |
| Platform | restart of the `morninger` process to watch the `l1_route` job fire | not run; delivered later by US-015 |

## Evidence

```
cd project
C:/venvs/news-scape/Scripts/python.exe -m pytest tests/ -q
...
395 passed, 550 warnings in 135.10s (0:02:15)
```

- Targeted subset during development: `pytest tests/test_raw_store.py tests/test_morninger.py tests/test_cafef_capture.py tests/test_backfill_deferred.py tests/test_cafef.py -q` gave 45 passed in 18.40s.
- Harness delta: backlog #6, the normal-lane context budget (at most 15 files) was too tight for a full-pipeline audit. This trace scored only `score_context=0.6` despite being complete and honest.
- Harness delta: backlog #7, the internal `project/.venv` was broken (pointing to Python 3.14 of an old Windows profile), against `AGENTS.md` §3.
- Trace #45: two Explore subagents in parallel, three gaps found, `morninger.py` confirmed as the real production scheduler (not `orchestrator.start_scheduler`, locked by Fix F).
- The trace confirmed the 8 enabled domains have Bronze raw capture and asked the user two decisions (capture interval, deferred drain cadence). It changed 6 product files and 4 test files; 23 files read.
- Files changed: `project/config/settings.yaml`, `project/src/crawler/raw_store.py`, `project/src/scrapers/capture_mixin.py`, `project/scripts/maintenance/backfill_deferred.py`, `project/src/morninger.py`, `project/scripts/pipeline_radar.py`.
- Test files changed: `project/tests/test_raw_store.py`, `test_cafef_capture.py`, `test_backfill_deferred.py`, `test_morninger.py`.
