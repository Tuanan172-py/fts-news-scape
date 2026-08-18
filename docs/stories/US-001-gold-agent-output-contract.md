# US-001 — Gold-layer agent OUTPUT contract (JSON Schema) — first slice

- **Status:** in_progress
- **Lane:** high-risk
- **Parent / Epic:** Phase 3 — Gold / agent-extract
- **Intake date:** 2026-08-18
- **Depends On:** none

> **Dogfood story** — the first real work run through the H1 harness to validate the loop.

## Intake (step 2 output)
```
Lane: high-risk
Reason: touches a public DATA CONTRACT (agent handoff OUTPUT envelope) = HARD GATE.
        Flags: Data contract, Weak proof (no Gold tests yet), Existing behavior (handoff contract in design).
Docs:  project/docs/design/09-agent-io-contract.md, 08-handoff-contract-catalog.md,
       project/docs/design/00-end-to-end-architecture.md (Vòng 3)
Story: docs/stories/US-001-gold-agent-output-contract.md
Validation: (proposed) python -m pytest tests/test_agent_output_contract.py
```

## Product Contract
Define the machine-checkable **agent OUTPUT** JSON Schema for the Gold layer (Vòng 3 `agent_ingest` DoD): the envelope an external agent must return per article so `agent_ingest` can validate before writing `agent_outputs`. Must align with the existing handoff INPUT contract and the exactly-once invariant (`UNIQUE(article_id, raw_sha256)`).

## Acceptance Criteria
- [ ] A versioned schema `agent-output-v1` exists (fields, types, required, enums).
- [ ] A pytest validates a golden sample (pass) + a malformed sample (fail).
- [ ] `agent_ingest` DoD references the schema (no silent divergence).

## Design Notes
Smallest real slice = the schema file + its validation test only; NOT the full `agent_ingest` implementation. Gold code is deferred by design — this locks the *contract* first (Producer↔Consumer boundary). Must not weaken existing WORM/exactly-once guarantees.

## Validation
| Tier | Command | Status | Evidence |
|------|---------|:------:|----------|
| Unit | `cd project; python -m pytest tests/test_agent_output_contract.py` | not run | schema + test not yet authored |
| Integration | — | — | |
| E2E | — | — | |
| Platform | — | — | |

## Harness Delta
- Backlog entries #1–#3 filed (status-not-queryable, WIP=1 unenforced, SESSION-LATEST debt) — see [../HARNESS_BACKLOG.md](../HARNESS_BACKLOG.md).
- This story hit a **hard gate** → an ADR is required before implementing (contract shape is a durable decision). ADR to be created in [../decisions/](../decisions/) after the human decision.

## Evidence
None yet — correctly. Per "no proof = not implemented", status stays `in_progress` and no tier is marked passed.

## Trace (inline, H1)
- **Actions:** classified request → intake (high-risk, data-contract hard gate) → read Vòng-3 design docs (context) → drafted story → **stopped at the hard gate** per HARNESS.md §9.
- **Files read:** project/docs/design/00, 08, 09 (to be read in the implementing session).
- **Files changed:** docs/stories/US-001-*.md (this file), docs/TEST_MATRIX.md (proof row).
- **Outcome:** blocked
- **Blocker:** HARD GATE — defining a public data contract requires a human decision (schema shape, versioning, backward-compat) before code. Awaiting go-ahead + ADR.
- **Friction:** none new beyond backlog #1–#3.
