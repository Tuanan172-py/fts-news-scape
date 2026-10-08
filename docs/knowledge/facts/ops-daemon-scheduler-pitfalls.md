---
id: FACT-ops-daemon-scheduler-pitfalls
type: fact
title: ops_daemon Task Scheduler pitfalls
status: active
created: 2026-10-01
updated: 2026-10-06
verified: 2026-10-01
lang: en
authors: [claude-opus-5-5]
adr: [ADR-0012, ADR-0014]
evidence:
  - "path: project/src/ops/procrun.py"
  - "path: project/src/agent/agy_runner.py"
  - "path: project/src/ops/dbos_flow.py"
  - "path: project/src/ops/control_room.py"
  - "path: project/docs/operations/ops-daemon.md"
  - "commit: 579163c"
summary: ops_daemon only behaves under Task Scheduler with priority 4, suspended job attach, resolve_agy, a localhost control room without SO_REUSEADDR, and levels L0 and L1 only.
---

# FACT-ops-daemon-scheduler-pitfalls — ops_daemon Task Scheduler pitfalls

## Fact

- The control plane is `project/src/ops/` with Task Scheduler tasks `news-scape-ops` (daemon) and `news-scape-ops-watchdog`.
- Since 2026-10-01 the ladder has only L0 (report) and L1 (run fully through DB ingest, no per-wave approval). It runs only while the machine is on.
- Task priority MUST be 4. The default 7 means low CPU and I/O priority, inherited by children: the sensor took 1.3 s by hand and 396 s in the task.
- The venv `python.exe` is a launcher whose job has `SILENT_BREAKAWAY_OK`. Create the child suspended, attach it to the daemon job, then resume (`procrun.popen_in_daemon_job`).
- Attaching after the process starts lets grandchildren escape the job.
- The user PATH holds an unexpanded `%LOCALAPPDATA%\agy\bin`. Under Task Scheduler a bare `agy` fails with WinError 2; use `agy_runner.resolve_agy()`.
- Articles of a wave not yet DONE or CANCELLED stay reserved in `ops_wave_articles`. An article packed twice is not retried automatically; `/cancel <wave>` releases it.
- DBOS `APP_VERSION = ops-v2`. Bump it only when the order or number of `drive_wave` steps changes.
- Git Bash turns `/status` into a path; send commands without the slash (`ops_daemon.py send status`).
- `ops_spans` traces flow through env `OPS_TRACE_DB/WAVE/PARENT`. Only `AgyRunner` is measured; the OpenRouter runner and OpenCode adapter are not.
- The control room (`ops_daemon.py open`, http://127.0.0.1:8787) listens on localhost only. On Windows `SO_REUSEADDR` allows a duplicate bind, so it sets `allow_reuse_address = False`.
- The 30-day mandate renews itself while healthy but is never re-granted once expired or never granted. The daemon stays at L0 until a human types `/level L1`.
- Improvement proposals come from the `improvement-proposer` operator, not an LLM agent; `harness-auditor` is still a draft.

## Why

- These behaviors appear only under Task Scheduler or in a real wave; unit tests do not catch them.

## How to Apply

- When editing `src/ops/`, run `tests/test_ops_*.py`, which include a real Job Object test (B3).
- While the daemon is at L1, MUST NOT open manual waves in parallel.
- The Telegram bot token was exposed in the bot creation chat; remind the operator to run `/revoke`.
