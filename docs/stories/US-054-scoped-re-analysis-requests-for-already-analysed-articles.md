---
id: US-054
type: story
title: Scoped re-analysis requests for already-analysed articles
status: implemented
lane: high-risk
created: 2026-11-17
updated: 2026-11-17
lang: en
authors: [agent]
adr: [ADR-0032]
plan: []
evidence:
  - path:project/src/db/store.py
  - path:project/scripts/article_pack.py
  - path:project/scripts/maintenance/request_reanalysis.py
  - path:project/tests/test_reanalysis_requests.py
verify: "C:/venvs/news-scape/Scripts/python.exe -m pytest project/tests/test_reanalysis_requests.py project/tests/test_article_contract.py -q"
summary: An operator can request a fresh analysis for articles that already passed the DoD, while the old result stays published until a better one replaces it.
---

# US-054 — Scoped re-analysis requests for already-analysed articles

## Contract

After this story an operator can ask the Article Lane to analyse a chosen set of articles again, by id list or by date range. The unattended `ops_daemon` selects those articles through its normal backlog rule, so no manual wave runs beside it. The old analysis stays valid and published until a new output passes the DoD in both layers. A failing new output never replaces the older passing one while the request is open. Without a request, every selection and ingest rule behaves exactly as before.

## Acceptance Criteria

- [x] R-A: `reanalysis_requests` and `reanalysis_archive` tables exist; opening a request archives the current passing outputs of both layers first.
- [x] R-B: `load_candidates(only_pending=True)` returns an analysed article while its request is open and stops returning it when both layers hold a passing output created at or after the request.
- [x] R-C: `ingest_output` in both runners ignores a cached passing output older than the open request, so the new result is stored instead of being treated as a replay.
- [x] R-D: `insert_agent_output` and `insert_l1_output` keep the older passing row when a failing row arrives during an open request; outside a request the old behaviour is unchanged.
- [x] R-E: `scripts/maintenance/request_reanalysis.py` defaults to a dry run, supports `--ids-csv`, `--date-range` and `--status`, and resets the attempt counter in `ops.db` so the daemon does not skip the article.
- [x] R-F: requests for the 174 title-summary mismatches and the 9,720 articles of 2026-11-01 to 2026-11-12 are filed.

## Design Notes

- Flipping `dod_pass` to 0 was rejected: `sync_master` retracts every article that is no longer passing, the guard limit is 5% of the master (`DEFAULT_MAX_RETRACT_RATIO`), and about 9,900 articles exceed it. Even below the limit the articles would vanish from Production until re-analysed.
- A request closes by comparing timestamps, so no flag needs a second writer and a crashed wave leaves no stale state.
- `requeue.py`, `l1_route.py` and `agent_export.py` stay retired (AGENTS.md); the script only adds a request row and archives outputs, it does not touch `work_items` or `l1_tasks` status.
- `ops_article_attempts` is reset for the requested ids because the daemon excludes articles that reached `max_attempts_per_article`.
- Cost: the 2026-11-01 to 2026-11-12 range holds about 9,700 analysed articles; the daemon processes them under the T4 rule (19:00 to 07:00 and weekends), newest day first.
- Rollback: drop the two tables; selection and ingest then fall back to the old condition because the code checks that the table exists.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `pytest project/tests/test_reanalysis_requests.py` | pass (8) |
| Integration | Full `project/tests` | 1165 passed, 0 failed before the preset cutover |
| Platform | First daemon wave after the cutover to the `ek` prefix | W11171504 DONE 38/38 after the daemon restart; W11171521 DONE 27/27 |

## Evidence

- Prefix cutover on 2026-11-17: backup in `C:\data\news-scape\state\backup_20261117`; `refresh_aliases.py` updated 40 entities; prefix hash `5d270579e6077b3e`, 20,628 characters; the preset persona was written by `build_article_prefix.py --sync-preset` and `--check` passes.
- Waves W11171457 and W11171459 were parked at preflight for about six minutes because the generator changed before the file on disk; both were cancelled with `release_stale_waves.py`.
- Wave W11171504 was parked at 13% coverage because the long-running daemon still held the old validator and rejected `ek`; after `schtasks /End` and `/Run` of `news-scape-ops` and `/retry` it finished 38/38.
- Incident: the first request run held one long write transaction on `monocle.db`; wave W11171521 failed `--finish` with `database is locked` and the daemon demoted itself from L1 to L0. The writer now commits chunks of 20 articles. Wave W11171521 was retried to DONE 27/27 and the L1 mandate to 2026-11-25 was restored with `ops_daemon.py order --level L1 --days 8`.
- The daemon closes the requests over the next nights under the T4 rule; the run is tracked as item R5 in `docs/OPEN-ITEMS.md`, read with `request_reanalysis.py --status` (8 of 174 mismatches were closed within the first hour).
- Counters: 9,720 + 174 articles requested; attempts reset for the requested ids so the daemon does not skip them.
- Incident on 2026-11-17 19:05: the first T4 re-analysis wave W11171902 failed ingest with 17 of 100 records `citation not grounded`. Their work packages still held the RSS excerpt of the first analysis, while the packer sent the full Silver body. `AgentRunner.ingest_output` now rebuilds a package when Silver exists and differs (`test_goi_viec_cu_tu_rss_duoc_dung_lai_tu_silver_khi_phan_tich_lai`). After the daemon restart, `/retry W11171902` finished DONE 100/100 with 0 failed.
- Audit on 2026-11-17 20:00: 50 of the 174 `us053-title-mismatch` requests could never run because their attempt counters were not reset; that batch was filed in the 15:21 run that stopped on a lock before `reset_attempts`. The counters were reset with `OpsStore.reset_attempts`. Check with a join of `reanalysis_requests` and `ops_article_attempts` where `attempts >= max_attempts_per_article` and `updated_at < requested_at`.
- Incident on 2026-11-18 19:18: T4 wave W11181913 failed the 5-minute prepare deadline (301 s), like W11180700 at 07:05. T4 prepare over 2023-04-27..now grew from a median of 58 s to 200–300 s. `deadlines_minutes.prepare` was raised to 10 in `config/ops.yaml` (390d6b2); after the daemon restart `/retry W11181913` finished DONE at 19:37.
- Completion on 2026-11-18 22:49: the daemon closed every request it could run during the T4 window; 0 waves failed after 19:37 and the L1 mandate renewed itself to 2026-12-18.
- One `us053-title-mismatch` request (`e31771dbd270…`) could never close because its article no longer exists in `articles`. With the user's approval it was closed by hand on 2026-11-19: a `request_closed` row in `reanalysis_archive` records the request and reason, and the row was removed from `reanalysis_requests`.
- Final `request_reanalysis.py --status` on 2026-11-19: `us053-entities-1101-1112` 9684/9684, `us053-title-mismatch` 173/173, 0 open.
- Root cause of the slow T4 prepare (2026-11-19): the request-closing subquery used the `(dod_pass, created_at)` index on `agent_outputs` and scanned every newer output per request. With unary `+` on those columns the selector took 9.9 s instead of 594 s (same 16 rows), and `request_reanalysis.py --status` took 2 s instead of over 30 min. See FACT-sqlite-correlated-range-index.
- Regime check on 2026-11-19: on Production the share of articles with an entity is 80–89% for 2026-11-01..12 (25–33% up to 2026-10-31), the same as after 2026-11-13. The plugin regime start in `config/regimes.json` moved to 2026-11-01, so `buzz` uses 18 baseline days instead of 6.
