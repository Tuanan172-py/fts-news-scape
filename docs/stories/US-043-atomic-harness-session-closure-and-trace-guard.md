---
id: US-043
type: story
title: Atomic Harness Session Closure and Trace Guard
status: implemented
branch: dev/us038
lane: normal
created: 2026-10-08
updated: 2026-10-08
lang: en
authors: [operator, antigravity]
adr: []
plan: []
evidence: []
verify: "pytest tests/test_harness_cli.py -k test_session_close -q"
summary: Implement atomic harness session close command and C-Light git trace guard.
---

# US-043 — Atomic Harness Session Closure and Trace Guard

## Contract

The harness must provide an atomic session closure command (`harness_cli.py session close`) that unifies verification proof execution, story state progression, git commit creation, durable trace persistence, and markdown closure table rendering into a single command. A C-Light guard must detect commits lacking durable trace records without blocking manual developer workflows.

## Acceptance Criteria

- [x] `harness_cli.py session close` executes verification gate, marks story implemented, creates atomic git commit, and records trace into `harness.db`.
- [x] `harness_cli.py session close` renders the exact Markdown Harness Closure Protocol table on stdout.
- [x] `cmd_git_status` provides C-Light trace check identifying commits without trace records.
- [x] All unit tests for session closure and trace verification pass cleanly in `tests/test_harness_cli.py`.

## Design Notes

- Implements Hybrid Strategy (B + C-Light) approved following tradeoff analysis.
- Consolidates fragmented 5-step manual closure into `cmd_session_close`.
- C-Light guard flags missing traces in `cmd_git_status` without hard-breaking human hotfixes.
- Conforms to Rule 04 and AGENTS.md §0 / §12.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `pytest tests/test_harness_cli.py -k test_session_close -q` | 2/2 PASS |
| Integration | `pytest tests/test_harness_cli.py -q` | 13/13 PASS |
| Platform | `python scripts/harness_cli.py session close --help` | PASS |

## Evidence

- `trace:harness_session_close`
