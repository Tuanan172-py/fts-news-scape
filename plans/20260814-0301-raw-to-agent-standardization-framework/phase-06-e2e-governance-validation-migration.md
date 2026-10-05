# Phase 06 — End-to-End Workflow Governance + Validation/Migration

## Context links
- All prior phases (1–5) + both research reports + `scout/scout-01-codebase.md`.
- Existing docs: `project/docs/design/06-raw-html-capture.md`, `project/docs/dev/06-raw-html-capture-guide.md`.
- Code: `project/src/handoff/contract_validator.py` (Phase 3), `project/src/db/store.py`, capture pipeline.

## Overview
- **Date:** 2026-08-14 · **Priority:** MEDIUM (stitch + harden; after 1–3 land, 4–5 authored).
- **Description:** Single end-to-end governance doc tying producer (Bronze→Silver→version→work-package→catalog)
  to agent contract (INPUT=work-package, OUTPUT=agent-output-v1, DoD). Wire hard schema-validation gate
  (producer-side). Define schema versioning/migration + a validation script proving the full chain.
- **Implementation status:** NOT STARTED · **Review status:** NOT REVIEWED.
- **Type:** IMPLEMENT (validation/migration code + governance doc). No agent/LLM code.

## Key Insights
- Everything upstream produces artifacts with schemas; governance = enforce them at boundaries + version them.
- One validator (Phase 3) serves BOTH work-package and agent-output (DRY) — Phase 6 just wires it as a gate + CI.
- Migration = additive/versioned (BACKWARD_TRANSITIVE); provide a re-derive path (Bronze→Silver→package) so schema
  bumps re-generate downstream WITHOUT re-scraping (raw immutable = source of truth).

## Requirements
**Functional**
- F1: `docs/design/11-e2e-standardization-governance.md` — the map: layers, contracts, states, DoD, versioning,
  who-owns-what, reconcile paths. Links (no dup) to docs 06–10.
- F2: Validation gate: `contract_validator` invoked on every emitted work-package (Phase 3) — fail → item `held`,
  logged, not enqueued as pending. (Wire, not new validator.)
- F3: `scripts/validate_e2e.py` — smoke test the whole chain on a sample: Bronze→Silver→version→package→
  schema-valid; + validate the hand-written agent-output sample (Phase 4) → proves contract round-trip. NO LLM.
- F4: Migration/versioning policy + `scripts/rederive_from_bronze.py` — regenerate Silver+packages from Bronze
  for a schema bump (idempotent, offline).
- F5: CI check (optional): validate all `schemas/*.schema.json` self-consistency + samples pass.
**Non-functional**
- No re-scrape needed for schema changes (raw is WORM source of truth). Idempotent re-derivation.

## Architecture
```
Bronze(raw) ─► Silver ─► article_versions ─► work-package ──[contract_validator gate]──► catalog(pending)
                                                                   │ fail
                                                                   └► held + log (reconcile)
INPUT(work-package) ─► [agent, Phase 4/5 spec] ─► OUTPUT(agent-output-v1) ─[contract_validator]─► (future DB)
schema bump: bump version -> rederive_from_bronze (Silver+packages) -> re-validate -> re-enqueue
```

## Related code files
- CREATE `project/docs/design/11-e2e-standardization-governance.md` (master governance map; links docs 06–10).
- MODIFY `project/src/scrapers/capture_mixin.py` (or handoff enqueue path) — enforce validator gate before enqueue
  as `pending`; on fail → `held` + log. (Reuse Phase 3 validator; no new logic beyond the gate.)
- CREATE `project/scripts/validate_e2e.py` — chain smoke test + sample-output validation.
- CREATE `project/scripts/rederive_from_bronze.py` — regenerate Silver+packages for schema bump (offline, idempotent).
- MODIFY `project/requirements` — ensure `jsonschema` present (from Phase 3).
- OPTIONAL CREATE `.github/workflows` step or `scripts/check_schemas.py` — schema+sample CI validation.

## Implementation Steps
1. Write governance doc 11: end-to-end diagram, layer/contract table, catalog-status ↔ lifecycle-state map,
   DoD summary, versioning/migration policy (additive, BACKWARD_TRANSITIVE, re-derive path), ownership + reconcile.
2. Wire validator gate at enqueue: build package → `contract_validator.validate(package, work-package-v1)` →
   pass ⇒ enqueue pending; fail ⇒ enqueue `held` + error log. (Phase 3 already builds; add the gate check.)
3. `scripts/validate_e2e.py`: pick a captured article → build Silver → fingerprint/version → build package →
   validate package → validate the Phase-4 agent-output sample → print PASS/FAIL report. No network, no LLM.
4. `scripts/rederive_from_bronze.py`: for domain/date range, re-run Silver+package build (idempotent overwrite),
   re-validate, re-enqueue changed items. Proves schema bumps don't need re-scrape.
5. Versioning policy: document rule (additive/optional only; bump `*_schema_version`; deprecate ≥2 versions before
   removal). Add `schemas/CHANGELOG.md`.
6. (Optional) `scripts/check_schemas.py` for CI: load every schema, validate each sample, non-zero exit on failure.

## Todo list
- [ ] docs/design/11-e2e-standardization-governance.md (master map, versioning/migration, reconcile).
- [ ] Validator gate wired at enqueue (pass→pending, fail→held+log).
- [ ] scripts/validate_e2e.py (Bronze→...→package + agent-output sample; PASS/FAIL; no LLM).
- [ ] scripts/rederive_from_bronze.py (idempotent offline re-derivation for schema bumps).
- [ ] schemas/CHANGELOG.md + versioning policy documented.
- [ ] (Optional) scripts/check_schemas.py CI schema+sample validation.
- [ ] Tests: gate rejects bad package (→held); validate_e2e green on sample; rederive idempotent.

## Success Criteria
- `validate_e2e.py` runs OFFLINE and reports PASS across the full chain incl. agent-output sample.
- Every enqueued-pending work-package is schema-valid; malformed ones are `held` + logged (never handed to agent).
- A schema version bump can regenerate Silver+packages from Bronze via rederive script WITHOUT re-scraping.
- Governance doc 11 is the single entry point mapping producer↔agent contract, states, DoD, versioning.
- No agent/LLM code introduced; only validation/migration/governance.

## Risk Assessment
- R1 Gate blocks pipeline if validator over-strict → gate routes to `held` (non-fatal), logs, capture unaffected.
- R2 Re-derivation drift vs live DB → idempotent overwrite + `raw_sha256` re-verify; run on copy first.
- R3 Doc rot vs code → doc 11 links canonical schemas; CI schema check catches sample drift.
- R4 Versioning mistakes break consumers → enforce additive/optional + CHANGELOG + BACKWARD_TRANSITIVE rule.

## Security Considerations
- Hard schema gate at boundary = defense-in-depth against malformed/injected packages reaching agent.
- Re-derivation reads only WORM Bronze (trusted-as-captured) — no new fetch/network surface.
- Audit: gate failures logged with article_id + error (traceability); aligns with reproducibility mandate (researcher-02 §5).

## Next steps
- When agent lands (post-plan), reuse OUTPUT validator + DoD predicate as the acceptance gate; add `agent_outputs` DB table.
- Revisit GOLD layer only if a producer-side curated dataset becomes needed (currently agent OUTPUT = gold; YAGNI).
