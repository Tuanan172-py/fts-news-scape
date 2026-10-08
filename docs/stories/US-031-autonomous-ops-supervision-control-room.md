---
id: US-031
type: story
title: Autonomous ops daemon supervision and control room
status: implemented
lane: normal
created: 2026-10-01
updated: 2026-10-06
lang: en
authors: [An Pham Thanh, claude-opus-5-5]
adr: [ADR-0012, ADR-0014]
plan: []
evidence:
  - commit:579163c
  - path:plans/20261001-1500-supervisor-control-room/plan.md
  - path:plans/20261001-1100-autonomous-ops-24x7/plan.md
  - path:project/src/ops/trace.py
  - path:project/src/ops/control_room.py
  - path:project/src/ops/supervision.py
  - path:project/src/ops/mandate.py
  - path:project/src/ops/improve.py
  - path:project/scripts/ops_daemon.py
  - test:project/tests/test_ops_trace.py
  - test:project/tests/test_ops_supervision.py
  - metric:647 tests passed, control room screenshot on real data, 2026-10-01 (harness.db)
verify: "python -m pytest project/tests/test_ops_trace.py project/tests/test_ops_supervision.py project/tests/test_ops_core.py project/tests/test_ops_runtime.py project/tests/test_ops_council_fixes.py -q"
reconstructed: 2026-10-06
summary: The operator supervises the autonomous ops daemon instead of approving each wave; ops_spans traces, a local control room, Telegram exception reports and a self-renewing mandate show every agent, script and wave.
---

# US-031 — Autonomous ops daemon supervision and control room

## Contract

The operator only supervises and improves the process. For every wave the operator can see which agent, skill, script and tool ran, and how they interacted. Telegram reports exceptions instead of asking for approval of each wave.

## Acceptance Criteria

- [x] P0: table `ops_spans` and `src/ops/trace.py` record wave, step and batch spans; a manual `article_run.py` run writes no span.
- [x] P1: a local read-only HTTP control room serves `/api/state` and a live map built from the registry.
- [x] P2: wave Gantt, trace tree, agent cards and 7-day KPIs; `agent_metrics` is written per wave.
- [x] P3: Telegram supervision digest, exception alerts and the `/map`, `/trace`, `/agent` commands; per-wave approval buttons removed.
- [x] P4: a 30-day conditionally self-renewing mandate and a deterministic improvement inbox (`improvement-proposer`), approved through ADR-0014.
- [ ] P0 acceptance on a real daemon wave that yields a full trace tree. Not done at closure (harness.db evidence).

## Design Notes

- Scope set by the operator's delegate: the autonomous ops daemon plus supervision phases P0 to P4. The daemon foundation is also tracked as US-029 in `harness.db`; ADR-0012 cites US-029.
- Phase table and acceptance per phase come from the supervisor control room plan, section 6 (reconstructed from that plan).
- Span writes happen per step and per batch, never per article, so supervision does not slow the wave.
- Control room is local only (`http://127.0.0.1:8787`, `python scripts/ops_daemon.py open`). Remote access waits for IT (decision D-B).
- Open technical items listed in `docs/OPEN-ITEMS.md` OPS-2: spans for the OpenRouter and opencode runners, `harness-auditor` promotion, Arize Phoenix spike, golden set for quality.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `verify` command in frontmatter | 647 tests passed across the suite (harness.db, 2026-10-01) |
| Integration | control room rendered on real `ops.db` data | screenshot taken, 2026-10-01 |
| Platform | real daemon wave with full trace tree | not done at closure |

## Evidence

- Commit 579163c: `src/ops/*` (daemon, trace, control room, supervision, mandate, improve, notify), `ops_daemon.py`, `ops_console.py`, ADR-0012, ADR-0014 and the two plans.
- The same commit also carried ADR-0013, the doc lint and the presentation layer; those belong to US-033 and US-032.
- `harness.db` row US-031: parent epic "Autonomous Ops", status implemented, no stored commit.
