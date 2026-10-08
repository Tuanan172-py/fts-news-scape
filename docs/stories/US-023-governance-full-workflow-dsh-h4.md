---
id: US-023
type: story
title: Governance and full daily workflow on DSH (H4)
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
summary: A deferred plan to run triage, dedup, brief, verifier and auditor agents and the full 2026-09-17 L1/Gold workflow on DSH; abandoned when ADR-0010 retired that workflow.
---

# US-023 — Governance and full daily workflow on DSH (H4)

## Contract

- The governance agents (triage, dedup, brief, verifier, auditor) MUST run on the flash model inside DSH (reconstructed from the harness.db row).
- The full 2026-09-17 workflow MUST run for real on the operational database.
- Retired: deferred on 2026-09-17 by operator request; ADR-0010 then replaced that workflow with the Article Lane.
- Evidence limited to the harness.db row and the plan.

## Acceptance Criteria

- [ ] No model other than flash is used.
- [ ] `agent_metrics` has rows for every agent.
- [ ] `propose` generates a proposal.

## Design Notes

- Phase H4 of plan `20260917-1538-dsh-harness-integration`.
- The DB evidence records the deferral: "Hoan theo yeu cau: chua can tich hop H4 tai phien 17/09".

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | none recorded | not run |
| Integration | none recorded | not run |
| Platform | none recorded | not run |

## Evidence

- harness.db story row US-023; no trace row and no commit names this story.
