# Raw→Agent Standardization Framework

**Date:** 2026-08-14 · **Status:** PLANNED — APPROVED (all key decisions resolved) · **Owner:** producer team

End-to-end contract: **codebase = raw producer**, **agent = consumer**. Producer side = IMPLEMENT
(storage layers, change-detection log, work-package + catalog/index, handoff validator). Agent side =
SPEC/DESIGN ONLY (JSON Schemas + framework docs; NO agent/LLM code now — YAGNI). Goal: any provider agent
picks up standardized per-article work packages and emits canonical output (tóm tắt→hàm ý→mức độ quan trọng…).

Build ON existing raw-capture (RawStore `.html`+`.meta.json` = BRONZE; `content_sha256`+`url_title_hash`
already present). Do NOT duplicate `project/docs/design/06-raw-html-capture.md`.

## Scope split
- **IMPLEMENT (producer):** Phases 1, 2, 3, 6 (+ Phase 6 validators/migration).
- **SPEC-ONLY (agent, no LLM code):** Phases 4, 5. Only code touching agent side = a thin
  contract-validator (Phase 3/4) validating agent output vs schema. NO agent runtime, NO API calls.

## Phases
| # | Phase | Type | Status | Progress | File |
|---|-------|------|--------|----------|------|
| 1 | Storage layers + provenance (Bronze/Silver, partitioning) | IMPL | ✅ DONE | 100% | [phase-01](phase-01-storage-layers-and-provenance.md) |
| 2 | HTML change-detection + version log + reconcile | IMPL | ✅ DONE | 100% | [phase-02](phase-02-change-detection-version-log.md) |
| 3 | Work-package schema + catalog/index + watermark + validator | IMPL | ✅ DONE | 100% | [phase-03](phase-03-work-package-catalog-handoff.md) |
| 4 | [SPEC] Agent I/O contract + output field taxonomy | SPEC | ✅ DONE | 100% | [phase-04](phase-04-spec-agent-io-and-taxonomy.md) |
| 5 | [SPEC] Agent orchestration & governance (main/sub, loops, DoD) | SPEC | ✅ DONE | 100% | [phase-05](phase-05-spec-agent-orchestration-governance.md) |
| 6 | End-to-end workflow governance + validation/migration | IMPL | ✅ DONE | 100% | [phase-06](phase-06-e2e-governance-validation-migration.md) |

**Implementation status (2026-08-14):** All phases implemented (producer) / authored (spec). New tests green
(`test_change_detect`, `test_handoff` — 20 passed) + `scripts/validate_e2e.py` → PASS full chain. Downstream
runs OFFLINE from WORM Bronze (`src/pipeline`, `src/handoff`, scripts) — capture path untouched (zero regression).
Docs: `docs/design/07`–`11`, schemas `silver/work-package/agent-output-v1` + `task-lifecycle-v1` + samples + CHANGELOG.
Deviation: downstream decoupled from `capture_mixin` (offline re-derivable) instead of live-wired — safer, matches medallion.

## Acceptance → phase map
- Full raw body of every requested page, byte-exact, immutable → existing capture + P1 (Bronze contract).
- Organized/scientific layered storage (clean base for code) → **P1** (Silver per-article package).
- Log when HTML changes to reconcile next scrape → **P2** (version chain + states + selector-drift flag).
- Raw packaged so any-provider agent accesses/processes easily → **P3** (work-package) + **P4** (I/O contract).
- Standardized agent output fields (summary→implication→materiality…) → **P4** (canonical OUTPUT JSON Schema).
- Framework/flow/main-sub order/constraints/loops/definition-of-done → **P5** (governance doc, provider-agnostic).
- Exactly-once incremental handoff (watermark, processing-status) → **P3** catalog.
- Hard schema validation gate (producer-side validator) → **P3**/**P4** validator, wired in **P6**.

## Dependencies (order)
P1 → P2 (versions need Silver + fingerprints) → P3 (package points to Bronze+Silver, catalog tracks status).
P4 depends on P3 (input contract = work-package). P5 depends on P4 (output schema). P6 wires all + migration.
Phases 4–5 are docs/schema-only; can be drafted in parallel with P2/P3 but finalize after P3.

## Design decisions (justified in phase files)
1. Medallion: existing `data/raw_html/**` = BRONZE (keep, immutable). Add SILVER = per-article normalized JSON
   on disk beside raw + SQLite pointer. GOLD deferred (YAGNI — agent produces it later). On-disk JSON + SQLite
   index chosen (least churn vs current SQLite-centric design; raw already on disk).
2. Work-package = versioned JSON Schema, self-describing, POINTS to raw (raw_sha256) — never inlines bytes.
3. Catalog = SQLite `work_items` table (view over Silver) — enumerate pending + processing-status watermark.
4. Change-log = `article_versions` table: content_sha256 + structural fingerprint (SimHash64 + DOM tag-path);
   states NEW|UNCHANGED|CONTENT_CHANGED|TEMPLATE_DRIFT|SELECTOR_BROKEN. Reuse `_looks_complete`.
5. Agent I/O provider-agnostic via JSON Schema; docs map to OpenAI/Anthropic/Gemini structured-output.
6. Output taxonomy: canonical required/optional fields + value scales + versioning (see P4).
7. Orchestration spec: router→extractor→analyst→verifier→aggregator; loops (map-reduce, refine-on-low-conf,
   adversarial verify); task lifecycle + definition-of-done touchpoint; guardrails; no vendor lock.
8. Quality gates: JSON-Schema validation (hard) + optional LLM-as-judge (spec); producer contract-validator.

## Decisions — RESOLVED (2026-08-14, owner-confirmed)
1. **Silver store** → on-disk JSON beside raw + SQLite index. (P1)
2. **Change baseline** → FRESH from now: first capture = NEW baseline; diffing starts next scrape. No backfill. (P2)
3. **SimHash** → implement 64-bit inline (no new dep, KISS). (P2)  [default applied]
4. **Watermark** → per-article `processing_status` row. (P3)  [default applied]
5. **Catalog format** → SQLite `work_items` table (aligns with Silver-index choice). (P3)
6. **Agent scope** → SPEC-ONLY now: JSON Schemas + governance docs + 1 hand-written validated sample. NO agent/LLM
   code, NO reference harness. (P4/P5)
7. **Output taxonomy scope** → CORE required (summary, implication, materiality, confidence, citations); everything
   else (entities+ticker sentiment, event_type, sentiment, time_sensitivity…) OPTIONAL → any provider can pass. (P4)
8. **GOLD layer** → deferred (agent output IS gold). [default applied]

## Still-open (minor; default applied, revisit if needed)
- Soft-404 / page-removed vs template-broken distinction in version log (researcher-01 Q1) — heuristic in P2,
  refine when observed live.
