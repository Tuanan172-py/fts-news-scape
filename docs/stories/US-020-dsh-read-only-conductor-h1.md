---
id: US-020
type: story
title: DSH read-only conductor for the agent network (H1)
status: retired
lane: high-risk
created: 2026-09-17
updated: 2026-10-06
lang: en
authors: [unknown]
adr: [ADR-0009, ADR-0010]
plan: []
evidence: [commit:42bc104, commit:c6c2a56, path:plans/20260917-1538-dsh-harness-integration/plan.md, path:.agents/dsh/presets/news-scape-conductor/agent.cordis.yml]
verify: "historical: no verify command recorded"
reconstructed: 2026-10-06
summary: A read-only DSH conductor preset was configured for the agent network but never received its platform proof; the Article Lane conductor replaced this design.
---

# US-020 — DSH read-only conductor for the agent network (H1)

## Contract

- The preset `news-scape-conductor` MUST mount from `.agents/dsh/presets` (reconstructed from the harness.db row).
- In this phase the conductor MUST only read: it spawns no agent and writes nothing to the database.
- Retired: the DB status was `deferred` with configuration done; the Article Lane conductor (ADR-0010) later replaced the read-only H1 design.

## Acceptance Criteria

- [ ] The preset is discovered and skill `dsh-conductor` appears in the catalog.
- [ ] The radar exits 0 from inside the session.
- [ ] The SHA256 of `monocle.db` is unchanged and no new file appears under `data/`.

## Design Notes

- Phase H1 of plan `20260917-1538-dsh-harness-integration`; runtime decision in ADR-0009.
- Trace 54 shows the H1 and H2 configuration together: preset junction, `agent_l1` and PTC rows, skill rewrite, and the registry model moved from pro to flash.
- Trace 56 packaged the runbook, added `agent_gold` and deferred H3 and H4.
- The platform proof needed a GUI session opened by the operator; an agent cannot start a preset session from inside a session.
- The harness.db verify command is truncated to a SHA256 fragment, so no runnable command is recorded.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | none recorded | not run |
| Integration | none recorded | not run |
| Platform | operator GUI session with the preset | not run; story deferred to free WIP |

## Evidence

- Commit 42bc104 (2026-09-17) adds the DSH integration plan and its four phase files.
- Commit c6c2a56 (2026-09-18) adds the preset, `dsh-conductor` skill, DSH runbook and ADR-0009.
- harness.db story row US-020 and traces 54 and 56, both outcome `partial`.
