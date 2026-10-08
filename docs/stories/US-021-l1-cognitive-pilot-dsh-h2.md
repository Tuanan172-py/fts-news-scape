---
id: US-021
type: story
title: L1 cognitive pilot on DSH (H2)
status: retired
lane: high-risk
created: 2026-09-17
updated: 2026-10-06
lang: en
authors: [unknown]
adr: [ADR-0009, ADR-0010]
plan: []
evidence: [path:plans/20260917-1538-dsh-harness-integration/plan.md]
verify: "historical: no verify command recorded"
reconstructed: 2026-10-06
summary: A planned pilot of an in-process L1 agent on DSH behind a token approval gate; never run, and abandoned when ADR-0010 retired the L1 lane.
---

# US-021 — L1 cognitive pilot on DSH (H2)

## Contract

- An `agent_l1` subagent MUST run in-process with a two-tool I/O filter, the L1 persona and model `deepseek-flash` (reconstructed from the harness.db row).
- The conductor uses PTC and MUST pass the ADR-0008 approval gate before spending tokens.
- Retired: the DB status stayed `planned`; ADR-0010 retired the L1 lane and US-026 removed `agent_l1` from the preset.
- Evidence limited to the harness.db row and the plan.

## Acceptance Criteria

- [ ] One wave of 3 x 25 articles runs, with L1 DoD pass at or above 95%.
- [ ] One `agent_metrics` row is written.
- [ ] No `agy` call happens, and the approval gate shows before any spawn.

## Design Notes

- Phase H2 of plan `20260917-1538-dsh-harness-integration`.
- The `agent_l1` and PTC preset rows were configured under US-020 (trace 54) but no pilot wave ran.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | none recorded | not run |
| Integration | none recorded | not run |
| Platform | pilot wave on DSH | not run |

## Evidence

- harness.db story row US-021; no trace row and no commit names this story.
