# Phase 03 — Work-Package Schema + Catalog/Index + Watermark + Validator (Handoff Contract)

## Context links
- Research: `research/researcher-01-...` §4 (work package, catalog, data contract), §5 (idempotency/watermark/exactly-once).
- Research: `research/researcher-02-agent-framework.md` §1 (canonical INPUT contract).
- Scout: `scout/scout-01-codebase.md` (gaps 1,2,4: no package, no catalog, no producer↔consumer boundary).
- Code: Phase 1 Silver, Phase 2 versions, `project/src/db/store.py`, `project/src/core/models.py`.

## Overview
- **Date:** 2026-08-14 · **Priority:** HIGH (the actual producer↔agent handoff boundary).
- **Description:** Emit ONE self-describing versioned JSON work-package per article the agent consumes
  (points to raw, does NOT inline). Build a catalog (`work_items` SQLite table) so any consumer enumerates
  pending work + drives processing-status watermark (pending|claimed|done|failed) for idempotent exactly-once
  incremental handoff. Ship a producer-side contract-validator (validates package AND, later, agent output).
- **Implementation status:** NOT STARTED · **Review status:** NOT REVIEWED.
- **Type:** IMPLEMENT (producer). This is the boundary; agent side beyond this = SPEC (Phase 4/5).

## Key Insights
- Work-package = the INPUT contract (researcher-02 §1). Must be provider-neutral JSON, self-describing,
  and POINT to byte-exact raw (`raw_html_path`+`raw_sha256`) so agent can re-verify offline.
- Catalog decouples producer/consumer: producer appends work_items; consumer claims → done/failed. Idempotency
  key = `article_id` (=url_title_hash) + `raw_sha256`. Re-reading same package must not double-process.
- Reuse Phase 2 `changed_since` + version `state`: only CONTENT_CHANGED/NEW become pending re-handoff;
  UNCHANGED skipped; SELECTOR_BROKEN/TEMPLATE_DRIFT → `held` (not handed to agent until reconciled).
- SQLite table (not JSONL manifest) chosen for catalog: least churn (DB already central), transactional claim.

## Requirements
**Functional**
- F1: `schemas/work-package-v1.schema.json` — versioned JSON Schema for package (fields below).
- F2: `WorkPackageBuilder.build(article_id) -> package` assembling from Silver + capture meta + version state.
- F3: Write package to `data/work_packages/<domain>/<yyyymmdd>/<hash>.json` (atomic).
- F4: `work_items` catalog table + API: `enqueue`, `list_pending`, `claim(worker_id)`, `mark_done`, `mark_failed`.
- F5: Watermark/processing-status: states `pending|claimed|done|failed|held`; claim is transactional
  (single-writer / `BEGIN IMMEDIATE`), so exactly-once even with retries.
- F6: `contract_validator.py` — validate a work-package (and, Phase 4, an agent output) against its JSON Schema;
  CLI + importable. Hard-fail on schema violation.
**Non-functional**
- Provider-agnostic: pure JSON, no vendor fields. Backward-compatible schema evolution (additive/optional, versioned).
- Exactly-once: idempotent enqueue (INSERT OR IGNORE on `article_id+raw_sha256`); claim atomic.

## Architecture
```
Silver.json + capture meta + article_versions.state
        -> WorkPackageBuilder.build() -> work_package.json (atomic write, points to raw)
        -> work_items.enqueue(article_id, raw_sha256, package_path, state) [INSERT OR IGNORE]

consumer (any provider agent — Phase 4/5 spec):
  list_pending() -> claim(worker_id) [pending->claimed, atomic] -> process -> mark_done/mark_failed
  idempotency key = (article_id, raw_sha256)
```
- **Work-package fields (v1):**
  `schema_version, article_id(=url_title_hash), source_url, domain, published_at, raw_html_path,
   raw_sha256, cleaned_text, structure{headings,paragraphs,tables,links}, images[], capture_status,
   change_state, provenance{fetch_ts, render_method, scraper_version, silver_schema_version}`.
  MUST include `raw_sha256`+`raw_html_path` (re-verify), MUST NOT inline raw bytes.
- **work_items table:**
  `id PK, article_id, raw_sha256, domain, package_path, status, claimed_by, claimed_at, done_at,
   error, enqueued_at, change_state, UNIQUE(article_id, raw_sha256)`.
- Catalog index doubles as "manifest-of-manifests" via SQL view `catalog_view` (date, domain, counts, status).

## Related code files
- CREATE `project/schemas/work-package-v1.schema.json`.
- CREATE `project/src/handoff/work_package.py` — `WorkPackageBuilder` + atomic writer.
- CREATE `project/src/handoff/catalog.py` — `work_items` DDL + enqueue/list_pending/claim/mark_* (transactional).
- CREATE `project/src/handoff/contract_validator.py` — schema-validate package/agent-output (jsonschema); CLI.
- CREATE `project/src/handoff/__init__.py`.
- MODIFY `project/src/db/store.py` — register `work_items` DDL in `_SCHEMA` (or dedicated init in catalog.py).
- MODIFY `project/src/scrapers/capture_mixin.py` — after version insert, build package + enqueue (behind `handoff.enabled`).
- CREATE `project/scripts/enqueue_pending.py` — batch build+enqueue from Silver for a domain/date (offline).
- CREATE `project/docs/design/08-handoff-contract-catalog.md` — the producer↔consumer contract (single source of truth).
- ADD dep `jsonschema` to requirements.

## Implementation Steps
1. Author `work-package-v1.schema.json` (Draft 2020-12): required = schema_version, article_id, source_url,
   domain, raw_html_path, raw_sha256, cleaned_text, capture_status, change_state; optional = structure, images,
   published_at, provenance.
2. `WorkPackageBuilder.build(article_id)`: load Silver.json + capture meta + latest article_versions row →
   assemble package dict; set `raw_sha256`=meta.content_sha256, `raw_html_path`=meta.html_path.
3. Atomic write to `data/work_packages/...` mirroring partition.
4. `catalog.py`: create `work_items`; `enqueue` = INSERT OR IGNORE (idempotent); `list_pending(limit)`;
   `claim(worker_id)` = `BEGIN IMMEDIATE; UPDATE ... SET status='claimed' WHERE id=? AND status='pending'`;
   `mark_done(id)`, `mark_failed(id, error)`. Held: enqueue with status='held' when change_state in
   {SELECTOR_BROKEN, TEMPLATE_DRIFT}.
5. `contract_validator.py`: `validate(instance, schema_path) -> (ok, errors)`; CLI `python -m ... <file> <schema>`;
   used producer-side now for packages; reused Phase 4 for agent output. DRY: one validator, two schemas.
6. Wire capture_mixin behind `handoff.enabled` (default true): build package, enqueue, set `metadata["handoff"]`.
   Non-fatal on error.
7. `scripts/enqueue_pending.py`: enumerate Silver artifacts changed_since watermark → build+enqueue (offline batch).
8. Doc 08: define the contract, states, idempotency key, exactly-once claim protocol, and the "held" reconcile path.

## Todo list
- [ ] work-package-v1.schema.json authored + sample validates.
- [ ] WorkPackageBuilder + atomic writer (points to raw, no inline bytes).
- [ ] work_items table + enqueue(idempotent)/list_pending/claim(atomic)/mark_done/mark_failed/held.
- [ ] contract_validator.py (jsonschema) CLI + import; validates package.
- [ ] capture_mixin wiring behind handoff.enabled.
- [ ] scripts/enqueue_pending.py (offline batch from Silver + changed_since).
- [ ] docs/design/08-handoff-contract-catalog.md.
- [ ] tests: schema validation pass/fail, idempotent enqueue, atomic claim (no double-claim), held routing, watermark.

## Success Criteria
- Every consumable article has a schema-valid work-package pointing to raw (`raw_sha256` matches Bronze).
- `contract_validator` rejects a malformed package (missing required field) with clear error.
- Two concurrent `claim()` calls never double-claim the same item (transactional test).
- Re-enqueue of same (article_id, raw_sha256) is a no-op (idempotent).
- Consumer can enumerate pending, claim, mark done/failed; watermark advances; UNCHANGED skipped; broken → held.
- Agent (any provider) can read a package with zero producer-specific knowledge (pure JSON + JSON Schema).

## Risk Assessment
- R1 Package/raw drift (raw changed after package built) → package carries `raw_sha256`; consumer re-verifies; mismatch → re-enqueue.
- R2 Claim races under APScheduler threads → use BEGIN IMMEDIATE / single-writer; test concurrent claim.
- R3 Catalog growth → status-indexed queries; archive done rows via retention job (doc note; YAGNI now).
- R4 Schema evolution breaking consumers → additive/optional only, bump schema_version, BACKWARD_TRANSITIVE (researcher-01 §4).

## Security Considerations
- Package is pure data; no executable content; raw referenced by path+hash, not inlined (limits injection surface).
- Validator uses `jsonschema` (no code exec). Reject packages failing schema before any downstream use.
- No PII beyond already-whitelisted provenance (no cookies/auth headers — inherited from capture hygiene).

## Next steps
- Phase 4 (SPEC): define agent I/O contract with THIS work-package as canonical INPUT; author OUTPUT schema;
  reuse `contract_validator` for output validation.
- Phase 6 wires validator into a producer gate + migration.
