# Phase 04 — [SPEC-ONLY] Agent I/O Contract + Output Field Taxonomy

> **SPEC-ONLY. NO agent code, NO LLM calls now.** Deliverables = machine-readable JSON Schemas + written spec.
> Only code artifact = REUSE Phase 3 `contract_validator` to validate a sample/agent output vs the OUTPUT schema.

## Context links
- Research: `research/researcher-02-agent-framework.md` §1 (provider-agnostic I/O, MCP), §2 (output taxonomy), §5 (schema validation).
- Phase 3: `phase-03-work-package-catalog-handoff.md` (work-package = canonical INPUT).
- Existing DB slots: `project/src/db/store.py` (`sentiment`, `sentiment_score` columns already reserved).

## Overview
- **Date:** 2026-08-14 · **Priority:** MEDIUM (design; unblocks any-provider implementation later).
- **Description:** Define provider-agnostic INPUT (= work-package) and canonical OUTPUT JSON Schema so ANY
  provider agent (OpenAI/Anthropic/Gemini/local) produces identical standardized fields:
  summary(tóm tắt)→implication(hàm ý)→materiality(mức độ quan trọng)→entities+ticker sentiment→citations…
  Define value scales, required/optional, versioning, and provider mapping — in docs only.
- **Implementation status:** SPEC ONLY (no runtime) · **Review status:** NOT REVIEWED.
- **Type:** SPEC/DESIGN.

## Key Insights
- No universal cross-provider format (2026); convergence via JSON Schema (researcher-02 §1). Portability =
  encode I/O as JSON Schema + document provider mapping (OpenAI structured outputs / Anthropic tool use /
  Gemini responseSchema). Adapter code is OUT OF SCOPE (agent side, later).
- OUTPUT schema is the standardization payoff: fixed field names + scales → downstream comparability + DB storage.
- Citations grounded to raw offsets/blocks (researcher-02 §2, §5) — enables Phase 6 groundedness gate later.

## Requirements (deliverables — all docs/schemas)
- D1: `schemas/agent-output-v1.schema.json` — canonical OUTPUT (fields + scales + required/optional).
- D2: `docs/design/09-agent-io-contract.md` — INPUT=work-package (ref Phase 3), OUTPUT=schema, provider mapping,
  versioning policy (BACKWARD_TRANSITIVE), examples.
- D3: One valid sample output JSON that passes `contract_validator` (proves schema usable) — NO LLM, hand-written.

## Canonical OUTPUT taxonomy (encode in schema; bilingual field notes)
Required:
- `article_id` (=work-package article_id), `output_schema_version`.
- `summary` (tóm tắt): `{abstractive:string, key_points:[string]}`.
- `implication` (hàm ý): `{text:string, affected_parties:[string], impact_area: enum(market|regulatory|sentiment|supply_chain|geopolitical|other)}`.
- `materiality` (mức độ quan trọng): `{score: float[0..1], time_sensitivity: enum(urgent|today|this_week|this_month|archive)}`.
- `sentiment`: `{overall: float[-1..1], polarity: enum(negative|neutral|positive)}`.
- `event_type`: enum(earnings|acquisition|regulatory|lawsuit|partnership|financial_move|macro|other).
- `entities`: `{companies:[{name, ticker|null, sentiment: float[-1..1]}], people:[{name, role|null}], locations:[string]}`.
- `confidence`: float[0..1].
- `citations`: [{claim:string, source_span:string, source_offset: int}] (grounded to work-package cleaned_text offsets).
- `processing_metadata`: `{agent_provider, model_used, timestamp(ISO8601), schema_version}`.

Optional: `entities.financial_instruments[]`, `sentiment.sentence_sentiments[]`, `processing_notes.warnings[]`,
`summary.key_quotes[]`, `extraction_quality: enum(high|medium|low)`.

Scales/rules: scores clamped to stated ranges; enums closed; ≥ required fields non-null; citations offsets must
index into work-package `cleaned_text`. Versioning: additive/optional only; bump `output_schema_version`; keep old readable.

## Architecture (contract only)
```
INPUT  (Phase 3 work-package JSON)  ── any provider agent (later) ──►  OUTPUT (agent-output-v1.json)
                                                                         │
                                              contract_validator (REUSE) │ hard schema gate (Phase 6)
```
Provider mapping (documented, not coded):
- OpenAI: pass `agent-output-v1` as `response_format: json_schema`.
- Anthropic: expose as tool input_schema (tool use) / structured output.
- Gemini: `responseSchema` = agent-output-v1.
- Local/LiteLLM/MCP: MCP tool result validated against same schema.

## Related code files
- CREATE `project/schemas/agent-output-v1.schema.json` (schema only).
- CREATE `project/docs/design/09-agent-io-contract.md`.
- CREATE `project/schemas/samples/agent-output-sample.json` (hand-written valid example).
- REUSE (no new code) `project/src/handoff/contract_validator.py` to validate the sample (add schema to its known set).
- (Deferred, documented as future) DB mapping: how OUTPUT maps into `articles.sentiment/sentiment_score` +
  a future `agent_outputs` table — NOTE ONLY, do not implement.

## Implementation Steps (spec authoring)
1. Draft `agent-output-v1.schema.json` with fields/scales/enums/required above (Draft 2020-12).
2. Write doc 09: INPUT ref (Phase 3), OUTPUT field table (bilingual), scales, required vs optional, versioning,
   provider mapping table, groundedness/citation-offset rule.
3. Hand-write `agent-output-sample.json`; run `contract_validator` against it → must PASS. (Only executable step.)
4. Document (NOTE ONLY) downstream DB persistence mapping for when agent lands — no code.

## Todo list
- [ ] agent-output-v1.schema.json authored (fields, scales, enums, required/optional, versioning).
- [ ] docs/design/09-agent-io-contract.md (INPUT/OUTPUT, provider mapping, citation rule, versioning).
- [ ] agent-output-sample.json hand-written and passes contract_validator.
- [ ] DB persistence mapping documented as future note (no implementation).

## Success Criteria
- OUTPUT schema fully specifies standardized fields with closed enums + numeric ranges.
- Sample output validates green via reused `contract_validator` (proves any provider can target it).
- Doc 09 lets a dev on ANY provider implement the agent later with zero producer-code changes.
- No agent runtime / LLM code added (scope honored).

## Risk Assessment
- R1 Over-spec (fields agent can't reliably fill) → mark aggressively optional; keep required set minimal (summary, implication, materiality, confidence, citations).
- R2 Provider schema quirks (enum/nesting limits) → document mapping caveats in doc 09; keep nesting shallow.
- R3 Vietnamese field-name keys (tóm tắt) risk in code → use ASCII keys (`summary`,`implication`,`materiality`) + bilingual labels in doc (interop safety).

## Security Considerations
- Output is data-only; validator prevents malformed/injection payloads before DB write (Phase 6 gate).
- Citation source_span must be substring of cleaned_text (groundedness) — documented rule; enforced later by judge (Phase 6, optional).

## Next steps
- Phase 5 (SPEC): orchestration/governance that PRODUCES this OUTPUT from the work-package INPUT.
- Phase 6: wire OUTPUT schema into hard validation gate; document migration for agent landing.
