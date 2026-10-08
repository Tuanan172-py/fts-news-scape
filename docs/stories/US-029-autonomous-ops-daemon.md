---
id: US-029
type: story
title: Autonomous ops daemon with sensor, provider breaker, Telegram oversight and heartbeat
status: implemented
lane: high-risk
created: 2026-10-01
updated: 2026-10-06
lang: en
authors: [unknown]
adr: [ADR-0012, ADR-0014]
plan: []
evidence: [commit:579163c, commit:4e461cd, commit:2497137, commit:a2233b1, commit:2d47285, path:plans/20261001-1100-autonomous-ops-24x7/plan.md, path:project/scripts/ops_daemon.py, test:project/tests/test_ops_council_fixes.py, test:project/tests/test_ops_restart_lock.py, wave:W10011351]
verify: "python -m pytest tests/test_ops_core.py tests/test_ops_runtime.py tests/test_ops_council_fixes.py"
reconstructed: 2026-10-06
summary: The Article Lane runs unattended while the machine is on, through ops_daemon with a 100-article sensor, provider breakers, Telegram oversight and a heartbeat; wave W10011351 completed 100 of 100 through it.
---

# US-029 — Autonomous ops daemon with sensor, provider breaker, Telegram oversight and heartbeat

## Contract

- `ops_daemon` MUST run the Article Lane without an operator while the machine is on, registered as a Task Scheduler task (reconstructed from the harness.db row and ADR-0012).
- A sensor MUST open a wave when 100 articles are ready, and a breaker MUST stop calls to a failing provider.
- The operator MUST receive Telegram oversight and a heartbeat; ADR-0014 adds supervision traces and the control room.

## Acceptance Criteria

- [x] The DBOS crash-resume spike passes.
- [x] Ops tests pass 100%.
- [x] `ops_daemon once` runs on the operational DB without opening a wave.
- [x] The install script registers the scheduled task.

## Design Notes

- Plan `20261001-1100-autonomous-ops-24x7`; decisions in ADR-0012 and ADR-0014.
- Code lives in `project/src/ops/`, `ops_daemon.py`, `ops_console.py`, `ops_install.ps1` and `config/ops.yaml` (trace 91).
- Council findings B2 to B7 and R2 were fixed, with levels L0 and L1 and a watchdog (trace 95).
- A restart race was fixed on 2026-10-06: the daemon now waits for a stale lock with a grace period (trace 114).
- Frictions recorded: Task Scheduler priority 7 slowed I/O; an unexpanded `%LOCALAPPDATA%` in PATH; the venv launcher job used `SILENT_BREAKAWAY_OK`.
- The harness.db `git_commit` de34143 is the branch head at trace time, a US-030 commit; the ops code landed in 579163c, tagged US-031.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python -m pytest tests/test_ops_core.py tests/test_ops_runtime.py tests/test_ops_council_fixes.py` | pass; full suite 611 passed |
| Integration | watchdog chaos test and `ops_daemon once` on the operational DB | pass (traces 91 and 95) |
| Platform | real wave W10011351 through the daemon under Task Scheduler | DONE, 100 of 100 |

## Evidence

- Commit 579163c (2026-10-01) adds `src/ops`, the daemon scripts, ADR-0012, ADR-0014 and the plan.
- Commits 4e461cd and 2497137 (2026-10-06) fix the restart lock; cherry-picked to `dev/us038` as a2233b1 and 2d47285, with 191 ops and radar tests green.
- harness.db story row US-029 and traces 91, 95, 96, 114 and 115, all outcome `completed`.
