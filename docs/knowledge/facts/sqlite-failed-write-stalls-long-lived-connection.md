---
id: FACT-sqlite-failed-write-stalls-long-lived-connection
type: fact
title: A failed write on a long-lived SQLite connection stalls capture
status: active
created: 2026-11-17
updated: 2026-11-17
verified: 2026-11-17
lang: en
authors: [agent]
adr: []
evidence:
  - path:project/src/db/dedup.py
  - test:project/tests/test_dedup_lock_recovery.py
  - "metric: no article captured from 15:41 to 18:30 on 2026-11-17; every capture cycle ended silently after the first source"
summary: After one `database is locked` error, a long-lived Python sqlite3 connection keeps its deferred transaction open, so every later write fails at once until the process restarts; roll back on error.
---

# FACT-sqlite-failed-write-stalls-long-lived-connection — A failed write on a long-lived SQLite connection stalls capture

## Fact

- Python `sqlite3` opens a deferred transaction before an INSERT; when the INSERT fails with `database is locked`, the transaction stays open.
- The next read on that connection pins a WAL snapshot. Once another process commits, each write fails at once with SQLITE_BUSY_SNAPSHOT, and `busy_timeout` does not retry it.
- The connection never recovers by itself, because nothing commits or rolls back the open transaction.

## Why

- On 2026-11-17 a long re-analysis request write held `monocle.db` for over 30 s. `DedupCache.discover` in `morninger` failed once at 15:43.
- Capture then stopped for almost three hours, while the scheduler kept logging `Cycle start` every ten minutes.
- The exception escaped `Orchestrator.run_cycle` into APScheduler, which logs to stderr rather than the loguru file, so the log showed no error.

## How to Apply

- A connection kept for the life of a process MUST roll back when a write fails, and SHOULD roll back a leftover transaction before each use (`DedupCache._write`, `DedupCache._clear_stale`).
- Bulk maintenance writers on `monocle.db` MUST commit in short `BEGIN IMMEDIATE` chunks (`ArticleStore.request_reanalysis`).
- To diagnose a silent stall, sample the stacks with `py-spy dump --pid <pid>` (installed in `C:\venvs\news-scape`) and compare heartbeats in `scraper_heartbeat` with the newest `fetched_at`.
