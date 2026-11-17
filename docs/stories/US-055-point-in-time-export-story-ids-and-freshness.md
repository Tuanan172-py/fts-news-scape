---
id: US-055
type: story
title: Point-in-time export, story ids and freshness for Research users
status: implemented
lane: high-risk
created: 2026-11-17
updated: 2026-11-17
lang: en
authors: [agent]
adr: [ADR-0033]
plan: []
evidence:
  - path:project/src/lakehouse/ingest.py
  - path:project/src/research_db/production.py
  - path:project/src/research_db/master.py
  - path:project/src/ops/probes.py
  - path:project/src/ops/daemon.py
  - path:plugins/fpts-market-intel/tools/lakehouse_pit.py
  - path:plugins/fpts-market-intel/tools/lakehouse_client.py
  - test:project/tests/test_pit_export.py
  - test:project/tests/test_plugin_pit.py
verify: "C:/venvs/news-scape/Scripts/python.exe -m pytest project/tests/test_pit_export.py project/tests/test_plugin_pit.py project/tests/test_research_production.py project/tests/test_plugin_lakehouse_client.py -q"
summary: Research users query production news as it was known at any minute, count stories by content cluster, see holiday-correct sessions and data freshness, get faster lenses, and receive urgent stories on Telegram.
---

# US-055 — Point-in-time export, story ids and freshness for Research users

## Contract

After this story an analyst using `fpts-market-intel` can ask what was known at a given minute with `--cutoff`, without look-ahead from late captures. The analyst counts stories by content cluster instead of headline text and sees trading sessions that skip exchange holidays. The `status` lens shows how fresh production is and how much is still unpublished, and the common lenses run several times faster. The operator gets a warning when a source yields far fewer articles than usual, and a Telegram alert for urgent stories at each publish.

## Acceptance Criteria

- [x] D1: production partitions carry `first_seen_at`, `published_at_precision` and `analyzed_at`; old fragments consolidate with NULL in these columns (`test_pit_export.py`).
- [x] D2: the master mirrors `article_story` from `monocle.db`; a membership or source-count change rewrites only the affected day (`test_story_change_rewrites_the_day`).
- [x] D3: plugin `articles` exposes `available_at` and `capture_lag_min`, `--cutoff` filters on `available_at`, and `trade_date` follows `config/trading_calendar.json` (`test_plugin_pit.py`).
- [x] D4: `probe_yield` flags a source whose 120-minute yield is zero or below z = -2.5 against 10 past weekdays; bursty sources with frequent empty windows are not flagged.
- [x] D5: the manifest carries `obt_schema`, `columns` and `freshness`; plugin `status` shows them with `pit_coverage` and calendar warnings.
- [x] D6: the CLI caches built tables locally; on production `status` 0.9 s, `buzz` 2.2 s, `pulse` 2.3 s, `themes` 7.7 s on a hit.
- [x] D7: after a successful publish the daemon queues one `news` alert listing urgent stories grouped by `story_id`, captured within 12 hours, with a watermark so nothing repeats.
- [ ] Operator verifies the holiday lists (ADR-0033 follow-up).

## Design Notes

- The audit item "D8" (ADR-0032 event kind and re-analysis requests) belongs to US-053 and US-054, run by another session in the main worktree; this story does not touch those files.
- D6 deviates from the proposal of publisher-side rollups: timing showed the Parquet scan costs 0.3 s and view building about 9 s (FACT-lakehouse-client-cost-is-view-building-not-parquet).
- D7 selects only by the model label `urgent` (AGENTS.md section 7.3); a sub-minute alert on unlabelled captures was rejected in ADR-0033.
- The first publish after deployment rewrites most day partitions because every `article_story` row is new; expect one large OneDrive sync.
- The yield probe runs every minute in about 0.15 s on `monocle.db` (11 indexed range counts).

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `pytest tests/test_pit_export.py tests/test_plugin_pit.py` | pass (15 + 6) |
| Integration | Full `project/tests` without the three `test_empirical_challenger*` modules, which fail to import on HEAD | 1124 passed, 0 failed |
| Platform | Plugin lenses on production `FRA - Data/news` with cache; `probe_yield` on `monocle.db` at four sample times | timings above; probe flagged `thoibaotaichinhvietnam.vn` 2 articles against 30 usual on 2026-11-17 10:30 |

## Evidence

- Measurements in ADR-0033 and FACT-lakehouse-client-cost-is-view-building-not-parquet.
- Deploy audit on 2026-11-17 found capture stalled since 15:41: the `morninger` dedup connection kept a failed transaction open after a lock (FACT-sqlite-failed-write-stalls-long-lived-connection). The fix rolls back failed writes in `DedupCache` and isolates errors per source in `Orchestrator.run_cycle` (`test_dedup_lock_recovery.py`).
