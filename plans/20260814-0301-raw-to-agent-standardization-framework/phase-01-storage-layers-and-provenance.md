# Phase 01 — Storage Layers + Provenance (Bronze/Silver, partitioning)

## Context links
- Research: `research/researcher-01-storage-and-change-detection.md` §1–2, §4 (medallion, content-address, contract).
- Scout: `scout/scout-01-codebase.md` (gap 1: no clean-base package; reuse points).
- Existing (DO NOT duplicate): `project/docs/design/06-raw-html-capture.md`, `project/docs/dev/06-raw-html-capture-guide.md`.
- Code: `project/src/crawler/raw_store.py`, `project/src/core/models.py`, `project/src/db/store.py`,
  `project/src/processor/extractor.py` (trafilatura `extract_content(url, html)` — reuse for Silver).

## Overview
- **Date:** 2026-08-14 · **Priority:** HIGH (foundation for all phases).
- **Description:** Formalize existing `data/raw_html/**` as BRONZE (immutable, byte-exact — already built).
  Add SILVER = per-article normalized "clean base" package written to disk beside raw + SQLite pointer.
  GOLD deferred (YAGNI: agent produces enriched output later — Phase 4/5).
- **Implementation status:** NOT STARTED · **Review status:** NOT REVIEWED.
- **Type:** IMPLEMENT (producer).

## Key Insights
- Bronze ALREADY EXISTS and validated live: `RawStore` writes `<domain>/<yyyymmdd>/<url_title_hash>.html`
  + `.meta.json` (14 keys incl. `content_sha256`, `images[]`, `capture_status`). Do NOT rebuild it.
- `url_title_hash` = SHA-256(url+title) = stable article_id. `content_sha256` = SHA-256(raw bytes) = provenance key.
- Silver must be REPRODUCIBLE from Bronze offline (parser fix → re-run without re-hitting site). Raw stays WORM.
- Least-churn choice: Silver on disk (JSON, mirrors raw partition) + one SQLite pointer column, not a full DB blob.
- `content_html`/`content_text` already extracted inline in scraper — Silver formalizes + persists as versioned artifact.

## Requirements
**Functional**
- F1: Define BRONZE contract doc (immutability, layout, provenance) referencing existing capture — no code change.
- F2: `SilverBuilder.build(capture_meta, raw_bytes) -> silver_dict` — normalize raw into clean base:
  `cleaned_text`, `structure{headings[],paragraphs[],tables[],links[]}`, `images[]` (from meta), lang.
- F3: Write silver to `data/silver/<domain>/<yyyymmdd>/<url_title_hash>.json` (atomic tmp→replace, mirror raw partition).
- F4: Record Silver pointer: add `silver_path` + `silver_schema_version` into `Article.metadata["silver"]` and/or new DB column.
- F5: Silver build runs from Bronze artifact (offline-capable), idempotent (same raw → same silver, overwrite atomic).
**Non-functional**
- Backward-compatible: does not alter Bronze or existing `articles` schema semantics; additive only.
- Deterministic: no network in SilverBuilder; input = raw bytes + meta only.
- Partition parity with Bronze for time-window re-processing.

## Architecture
```
BRONZE (exists)                         SILVER (new)
data/raw_html/<domain>/<yyyymmdd>/       data/silver/<domain>/<yyyymmdd>/
  <hash>.html  (byte-exact, WORM)          <hash>.json  (normalized clean base)
  <hash>.meta.json (provenance)          pointer: articles.silver_path (+ metadata["silver"])

flow (offline-capable):
 raw bytes + meta.json --> SilverBuilder.build() --> silver.json (atomic write) --> DB pointer update
                              |__ reuse extractor.extract_content(url, html) (trafilatura)
                              |__ reuse capture images[] (no re-download)
```
- Silver JSON shape (input to Phase 3 work-package; keep flat, self-describing):
  `{silver_schema_version, article_id, source_url, domain, content_sha256, cleaned_text,
    structure{headings,paragraphs,tables,links}, images[], language, built_at, built_from_raw_path}`.
- Partitioning: identical `<domain>/<yyyymmdd>/` as Bronze → parallel re-extract by domain/date.

## Related code files
- CREATE `project/src/storage/silver_builder.py` — `SilverBuilder` (pure, no network).
- CREATE `project/src/storage/__init__.py`.
- CREATE `project/schemas/silver-v1.schema.json` — JSON Schema Draft 2020-12 for silver record.
- MODIFY `project/src/db/store.py` — add nullable columns `silver_path TEXT`, `silver_schema_version TEXT`
  (additive; `ALTER TABLE ... ADD COLUMN` idempotent guard). Add index optional.
- MODIFY `project/src/core/models.py` — `Article.metadata["silver"]` convention doc + `to_row()`/`from_row()`
  for new columns (default None; keep backward compat with old rows).
- MODIFY `project/src/scrapers/capture_mixin.py` — after successful capture, OPTIONALLY call SilverBuilder
  (behind config flag `silver.enabled`, default true) → set pointer. Keep raw-first invariant untouched.
- CREATE `project/docs/design/07-storage-layers-medallion.md` — Bronze/Silver contract, partitioning, provenance.
- CREATE `project/config/` silver block (raw_dir sibling): `silver: {enabled: true, dir: "data/silver"}`.

## Implementation Steps
1. Write `docs/design/07-storage-layers-medallion.md`: declare Bronze=existing raw (link doc 06, no dup),
   Silver spec, partition convention, immutability/WORM rules, provenance keys (`url_title_hash`, `content_sha256`).
2. Author `schemas/silver-v1.schema.json` (required: article_id, source_url, domain, content_sha256,
   cleaned_text, silver_schema_version, built_from_raw_path; optional: structure, images, language).
3. Implement `SilverBuilder.build(meta: dict, raw_bytes: bytes) -> dict`:
   - decode raw via meta.encoding (fallback utf-8, errors="replace"); reuse `extract_content(url, html)` for cleaned_text.
   - parse structure with BeautifulSoup (headings h1-h6, paragraphs, tables→list-of-rows, links{href,text}).
   - carry `images[]` straight from meta (already scanned; no re-download). set language via simple detect or meta.
   - set `content_sha256` = meta.content_sha256 (do NOT recompute unless verifying); `built_from_raw_path`=meta.html_path.
4. Implement atomic writer `write_silver(domain, yyyymmdd, hash, silver_dict)` (tmp→os.replace), mirror partition.
5. DB migration: guarded `ALTER TABLE articles ADD COLUMN silver_path`; same for `silver_schema_version`
   (check `PRAGMA table_info` before add — idempotent). Update `_COLUMNS`, `to_row`, `from_row`.
6. Wire in `capture_mixin`: after `capture_status in (ok, partial)`, build+write Silver, set pointer in metadata + row.
   Guard behind `silver.enabled`; on builder error → log, set `metadata["silver"]={"error":...}`, do NOT fail capture.
7. Add offline batch script `project/scripts/build_silver.py` — rebuild Silver from Bronze for a domain/date range
   (reads meta.json + .html, calls builder) → enables re-processing after parser fixes (YAGNI-safe, small).

## Todo list
- [ ] docs/design/07-storage-layers-medallion.md written (Bronze link, Silver spec, partitioning, provenance).
- [ ] schemas/silver-v1.schema.json authored + validates a sample.
- [ ] SilverBuilder implemented (pure, offline, reuses extractor + meta images).
- [ ] Atomic silver writer + partition mirror.
- [ ] DB additive columns migration (idempotent PRAGMA guard) + model round-trip.
- [ ] capture_mixin wiring behind config flag; raw-first invariant preserved.
- [ ] scripts/build_silver.py offline rebuild.
- [ ] Unit tests: builder determinism, structure parse, atomic write, migration idempotency, backward-compat rows.

## Success Criteria
- Given a captured raw `.html`+`.meta.json`, SilverBuilder produces schema-valid `silver.json` OFFLINE (no network).
- Silver partition mirrors Bronze; pointer resolvable from DB row and `metadata["silver"]`.
- Re-running build on same raw = byte-identical silver (deterministic); overwrite atomic.
- Existing capture tests still pass; Bronze artifacts unchanged (byte-exact, sha256 stable).
- Old `articles` rows load without error after migration (new columns null).

## Risk Assessment
- R1 Structure parse brittle across sources → keep structure OPTIONAL in schema; cleaned_text is the hard field.
- R2 Silver build slows capture → run behind flag; failure is non-fatal; offline rebuild script as fallback.
- R3 DB migration on live db → PRAGMA-guarded additive ALTER only; no data rewrite; test on copy first.
- R4 Disk growth (Silver ~ smaller than raw) → same `.gitignore` treatment as raw; note retention in doc.

## Security Considerations
- Silver derived from untrusted HTML → sanitize on parse (no eval; BeautifulSoup only). Do NOT execute scripts.
- Carry only whitelisted meta (already PII-hygiene'd in capture: no Set-Cookie/Authorization). Do not add headers.
- No secrets in silver.json; paths are relative repo paths.

## Next steps
- Phase 2 consumes Silver + Bronze fingerprints for the version chain/change-log.
- Phase 3 wraps Silver + Bronze pointer into the versioned work-package + catalog.
