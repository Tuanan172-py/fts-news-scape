---
id: US-059
type: story
title: Prevent ops daemon repair-cap deadlock and empty agy stream-json partial writes
status: implemented
branch: fix/ops-deadlock-agy-partial
lane: normal
created: 2026-11-26
updated: 2026-11-26
lang: en
authors: [agent]
adr: [ADR-0011, ADR-0012, ADR-0017]
plan: []
evidence:
  - "commit: a78ed30 (fix/ops-deadlock-agy-partial), 56f8cb7 (m1/us058-v3)"
  - "metric: 99 passed targeted ops+runner suite; 1195 passed, 21 skipped full suite; 124 passed on m1/us058-v3"
  - "wave: W11250821 (incident), W11261015..W11261038 (unblocked recovery waves DONE)"
verify: "C:/venvs/news-scape/Scripts/python.exe -m pytest project/tests/test_agy_runner.py project/tests/test_ops_runtime.py project/tests/test_ops_core.py project/tests/test_ops_council_fixes.py -q"
summary: A capped parked wave no longer deadlocks the ops daemon sensor loop, agy stream-json errors never write empty PARTIAL outputs, and provider outages do not burn wave repair rounds.
---

# US-059 — Prevent ops daemon repair-cap deadlock and empty agy stream-json partial writes

## Contract

When `agy` exits with code 0 in `stream-json` mode after a provider error or empty response, `AgyRunner` classifies it as `QUOTA`, `FATAL`, or `SOFT_FAIL`. It never falls back to raw NDJSON protocol stdout and never writes an empty `.output.json` file. When a wave in `repair` mode fails solely on `AUTH`, `QUOTA`, or `NETWORK` with zero progress, `WaveSteps.analyze` does not burn `repair_rounds` or article attempt limits. When a `PARKED` wave hits the repair cap, `OpsDaemon.sensor_tick` clears `resume_on_breaker = 0`, alerts once, and keeps opening new waves for remaining pending articles.

## Acceptance Criteria

- [x] `AgyRunner._run_batch_impl` never falls back to raw NDJSON `stdout_text` when structured `events` were parsed, classifies exit-0 `429`/auth/error stream events accurately, and never writes `[]` as `PARTIAL` when no valid records or domain errors exist.
- [x] `WaveSteps.analyze` skips `_count_repair_round` when `AUTH`, `QUOTA`, or `NETWORK` fails with zero progress or when the step is cancelled.
- [x] `OpsDaemon._sensor_tick` and `_retry_wave_locked` clear `resume_on_breaker = 0` when `repair_cap_reason` blocks a parked wave, emit `wave.retry_refused` once with a deduplicated alert, and continue the sensor tick so new waves open normally.
- [x] Regression tests cover all three root causes and the targeted ops + runner suites pass 100%.

## Design Notes

Fixes three cascading defects uncovered during the 2026-11-25 `W11250821` outage (`ops_logs/2026-11-25.jsonl`, `ops_logs/2026-11-26.jsonl`, `agent_outputs_article/article_W11250821_01.meta.json`):
1. `project/src/agent/agy_runner.py`: extract `error` / `result.status` / `result.error` from NDJSON events, check empty-response provider errors before validation, pass only `raw_response` when `events` is non-empty, and reject non-article JSON objects lacking `i` as `SOFT_FAIL`.
2. `project/src/ops/wave_flow.py`: defer `_count_repair_round` until after `executor` completes and skip it on zero-progress provider outages (`AUTH`, `QUOTA`, `NETWORK`) or operator cancellations.
3. `project/src/ops/daemon.py`: check `repair_cap_reason` before auto-resuming a parked wave, clear `resume_on_breaker = 0`, alert once, and `continue` instead of `return`.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `pytest project/tests/test_agy_runner.py project/tests/test_ops_runtime.py project/tests/test_ops_core.py project/tests/test_ops_council_fixes.py -q` | 99 passed |
| Integration | Full `pytest project/tests/ -q` on `fix/ops-deadlock-agy-partial`; ops+v3 targeted on `m1/us058-v3` | 1195 passed, 21 skipped (`fix/ops-deadlock-agy-partial`); 124 passed (`m1/us058-v3`) |
| Platform | Real-process `ops_daemon.py status` from fix worktree + live unblock (`W11261015`..`W11261038` DONE) | pass |

## Evidence

- Root-cause incident: `W11250821` (2026-11-25 10:53..2026-11-26 10:13).
- Commits: `a78ed30` (`fix/ops-deadlock-agy-partial`), `56f8cb7` (`m1/us058-v3`).
- AST docstring linter (100% coverage) and banned phrase scanner (0 violations) passed on `daemon.py`, `wave_flow.py`, `agy_runner.py`.
