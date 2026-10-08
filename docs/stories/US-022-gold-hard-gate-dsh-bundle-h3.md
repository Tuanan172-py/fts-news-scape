---
id: US-022
type: story
title: Gold hard gate and DSH harness bundle (H3)
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
summary: A deferred plan to hard-enforce the Gold activation gate on DSH and ship a local harness bundle; never built, and abandoned when ADR-0010 retired the Gold lane.
---

# US-022 — Gold hard gate and DSH harness bundle (H3)

## Contract

- `ns_activate` MUST hard-enforce the ADR-0008 activation gate (reconstructed from the harness.db row).
- A guard MUST enforce WIP and gate-before-advance, packaged as a local bundle `@news-scape/dsh-harness`.
- Retired: deferred on 2026-09-17 by operator request, then made moot when ADR-0010 retired the Gold lane.
- Evidence limited to the harness.db row and the plan.

## Acceptance Criteria

- [ ] The guard blocks `gold_export` while L1 is not green.
- [ ] `ns_activate` spawns nothing without confirmation.

## Design Notes

- Phase H3 of plan `20260917-1538-dsh-harness-integration`.
- The DB evidence records the deferral: "Hoan theo yeu cau: chua can tich hop H3 tai phien 17/09".

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | none recorded | not run |
| Integration | none recorded | not run |
| Platform | none recorded | not run |

## Evidence

- harness.db story row US-022; no trace row and no commit names this story.
