---
id: US-001
type: story
title: Gold-layer agent output contract (JSON Schema), first slice
status: retired
lane: high-risk
created: 2026-08-18
updated: 2026-10-06
lang: en
authors: [claude]
adr: [ADR-0010, ADR-0017]
evidence: ["commit:bb13847", "path:project/schemas/agent-output-v1.schema.json", "path:project/docs/design/09-agent-io-contract.md"]
verify: "historical: no verify command recorded"
original: "commit:bb13847"
reconstructed: 2026-10-06
summary: Dogfood story that stopped at the data-contract hard gate before the Gold agent output schema test was written; the Gold lane was later retired by ADR-0010.
---

# US-001 — Gold-layer agent output contract (JSON Schema), first slice

## Contract

- Define the machine-checkable agent OUTPUT JSON Schema for the Gold layer (round 3 `agent_ingest` DoD).
- The schema is the envelope an external agent returns per article, so `agent_ingest` can validate it before writing `agent_outputs`.
- It MUST align with the existing handoff INPUT contract and the exactly-once invariant `UNIQUE(article_id, raw_sha256)`.
- This was the dogfood story: the first real work run through the H1 harness to validate the loop.

## Acceptance Criteria

- [ ] A versioned schema `agent-output-v1` exists (fields, types, required, enums).
- [ ] A pytest validates a golden sample (pass) and a malformed sample (fail).
- [ ] `agent_ingest` DoD references the schema (no silent divergence).

## Design Notes

- Intake: lane `high-risk`, because the story touches a public DATA CONTRACT (agent handoff OUTPUT envelope), which is a hard gate.
- Intake flags: data contract, weak proof (no Gold tests yet), existing behavior (handoff contract in design).
- Context docs: `project/docs/design/09-agent-io-contract.md`, `08-handoff-contract-catalog.md`, `00-end-to-end-architecture.md` (round 3).
- Smallest real slice: the schema file plus its validation test only, not the full `agent_ingest` implementation.
- Gold code was deferred by design; the slice locks the contract first (producer and consumer boundary).
- The slice MUST NOT weaken existing WORM or exactly-once guarantees.
- The story stopped at the hard gate per `docs/HARNESS.md` §9. Schema shape, versioning and backward compatibility needed a human decision and an ADR before code.
- Reconstructed: `project/schemas/agent-output-v1.schema.json` already existed from commit 7adc68a (2026-08-17). The proposed test `tests/test_agent_output_contract.py` was never created.
- Reconstructed: the Gold output contract moved to `agent-output-v2-lean` and then to the unified Article Lane contract of ADR-0017.
- Retired: ADR-0010 ended the two-tier L1/Gold lane, so this Gold-only contract story has no remaining scope. The `harness.db` row says `blocked`.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `cd project; python -m pytest tests/test_agent_output_contract.py` | not run; schema test never authored |
| Integration | none | not run |
| Platform | none | not run |

## Evidence

- No proof was recorded. Per "no proof = not implemented", no tier was marked passed.
- Harness delta: backlog entries #1 to #3 filed (status not queryable, WIP=1 unenforced, SESSION-LATEST debt) in `docs/HARNESS_BACKLOG.md`.
- Trace (H1, inline): classified the request, ran intake (high-risk, data-contract hard gate), read the round 3 design docs, drafted the story, stopped at the hard gate. Outcome: blocked.
- Files changed at the time: `docs/stories/US-001-*.md`, `docs/TEST_MATRIX.md` (proof row).
