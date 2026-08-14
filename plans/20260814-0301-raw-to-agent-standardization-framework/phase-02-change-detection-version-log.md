# Phase 02 — HTML Change-Detection + Version Log + Reconcile

## Context links
- Research: `research/researcher-01-storage-and-change-detection.md` §3 (fingerprinting, change-log, states), §5 (watermarks).
- Scout: `scout/scout-01-codebase.md` (gap 3: no cross-run comparison; reuse `content_sha256`, `_looks_complete`).
- Code: `project/src/crawler/raw_store.py` (`content_sha256`), `project/src/scrapers/capture_mixin.py`
  (`_looks_complete`), `project/src/db/store.py` (add table), Phase 1 SilverBuilder (structure for DOM fingerprint).

## Overview
- **Date:** 2026-08-14 · **Priority:** HIGH (task explicitly requires change-log for reconcile).
- **Description:** Per-article version chain. On each (re)capture compute `content_sha256` (exists) +
  STRUCTURAL fingerprint (SimHash64 over tokens + DOM tag-path signature). Compare vs last version, classify
  change, log delta + selector-drift flag so producer/agent reconcile. States:
  NEW | UNCHANGED | CONTENT_CHANGED | TEMPLATE_DRIFT | SELECTOR_BROKEN.
- **Implementation status:** NOT STARTED · **Review status:** NOT REVIEWED.
- **Type:** IMPLEMENT (producer).

## Key Insights
- `content_sha256` gives exact-change detection but is too sensitive (any whitespace/ad flips it) → need
  fuzzy structural fingerprint (SimHash64) + DOM tag-path hash to separate content-change vs template-drift.
- SELECTOR_BROKEN reuses existing signal: `capture_status=partial` / `missing:[main_content_node]` /
  `_looks_complete=False` → mark selector drift so producer fixes extractor before agent consumes garbage.
- Version chain keyed by `url_title_hash` (article identity); each row = one capture instant → append-only log.
- KISS: implement 64-bit SimHash inline (hash tokens, weighted bit-vote) — avoid new dep (`simhash-py`) unless perf needs.

## Requirements
**Functional**
- F1: `fingerprint(raw_bytes, structure) -> {simhash64, dom_path_sig, selectors_present}`.
- F2: On capture, look up last `article_versions` row for `url_title_hash`; compute deltas
  (sha equal?, hamming(simhash), dom_sig equal?, selector present?).
- F3: Classify state:
  - no prior → NEW; sha equal → UNCHANGED; sha differ + hamming ≤ T_content → CONTENT_CHANGED;
  - dom_path_sig changed (hamming > T_template OR sig mismatch) → TEMPLATE_DRIFT;
  - capture_status partial/incomplete OR expected selector missing → SELECTOR_BROKEN (highest priority flag).
- F4: Append row to `article_versions` with prev pointer, state, distances, recommendation
  (skip | re_extract | manual_review).
- F5: Expose `changed_since(watermark)` query for Phase 3 catalog (which articles need re-handoff).
**Non-functional**
- Append-only (never mutate prior versions) — audit trail. Deterministic fingerprints.
- Cheap: O(n) tokenization once per capture; no extra network.

## Architecture
```
capture (raw bytes + Silver.structure)
   -> fingerprint(): simhash64, dom_path_sig, selectors_present
   -> load last article_versions[url_title_hash]
   -> compare -> STATE + recommendation
   -> INSERT article_versions(...)  (append-only)
```
- `article_versions` schema:
  `id PK, url_title_hash, source_domain, captured_at, content_sha256, simhash64 TEXT(hex),
   dom_path_sig TEXT, capture_status, prev_version_id, hamming_content INT, dom_changed INT,
   selector_drift INT, state TEXT, recommendation TEXT`.
- Thresholds config: `T_content` (e.g. hamming ≤ 6 = same-template content edit), `T_template`
  (dom_path_sig mismatch or large hamming). Store in `config` change_detection block.
- DOM tag-path signature: sorted multiset hash of root→node tag paths from Silver.structure (stable, ad-insensitive).

## Related code files
- CREATE `project/src/storage/change_detect.py` — `fingerprint()`, `classify(prev, cur)`, SimHash64 (inline).
- MODIFY `project/src/db/store.py` — add `article_versions` table (CREATE IF NOT EXISTS) + indexes
  (`idx_versions_hash(url_title_hash, captured_at)`), insert + last-lookup + `changed_since` methods.
- MODIFY `project/src/scrapers/capture_mixin.py` — after Silver build, compute fingerprint, classify, insert version.
  Non-fatal on error. Reuse `_looks_complete` result already computed for SELECTOR_BROKEN.
- CREATE `project/config` `change_detection: {t_content_hamming: 6, t_template: 12, enabled: true}`.
- MODIFY `project/docs/design/07-storage-layers-medallion.md` — add §change-detection (or new doc 08).
- CREATE tests `project/tests/test_change_detect.py`.

## Implementation Steps
1. Implement SimHash64 inline: tokenize cleaned_text (whitespace + lowercase), 64-bit hash per token,
   weighted bit vote → 64-bit fingerprint (hex string). Hamming = popcount(xor).
2. Implement `dom_path_sig`: from Silver.structure build sorted list of tag-paths (e.g. `article>div>p`),
   hash to stable signature (sha1 of joined sorted set, truncated) — ad/timestamp-insensitive.
3. `fingerprint(raw_bytes, structure)` returns dict; `selectors_present` = derived from capture missing[].
4. `classify(prev, cur)` implements F3 decision tree; SELECTOR_BROKEN takes precedence; return (state, recommendation).
5. DB: add `article_versions` + insert/last/`changed_since(watermark_iso)` methods (single-writer safe).
6. Wire in capture_mixin after Silver: load last, classify, insert. Attach `state` into `metadata["version"]`.
7. Reconcile hooks (doc + minimal): TEMPLATE_DRIFT/SELECTOR_BROKEN → recommendation `manual_review`; surface via
   `scripts/report_drift.py` (list drifted articles/domains) so producer fixes selector; agent skips broken packages.
8. Tests: NEW/UNCHANGED/CONTENT_CHANGED/TEMPLATE_DRIFT/SELECTOR_BROKEN cases with synthetic HTML pairs; hamming math.

## Todo list
- [ ] change_detect.py: SimHash64 + dom_path_sig + fingerprint + classify.
- [ ] article_versions table + insert/last/changed_since queries.
- [ ] capture_mixin wiring (append version, non-fatal), reuse _looks_complete.
- [ ] config change_detection thresholds.
- [ ] scripts/report_drift.py (list TEMPLATE_DRIFT/SELECTOR_BROKEN).
- [ ] docs update (change-detection section).
- [ ] tests for all 5 states + hamming/dom-sig determinism.

## Success Criteria
- Re-capturing identical raw → UNCHANGED (sha equal, hamming 0).
- Minor content edit, same template → CONTENT_CHANGED (hamming small, dom_sig same).
- Template/CMS change → TEMPLATE_DRIFT; missing main selector → SELECTOR_BROKEN with `manual_review`.
- `article_versions` append-only; prior rows never mutated; `changed_since()` returns correct set.
- `report_drift.py` lists drifted articles for reconcile.

## Risk Assessment
- R1 Threshold tuning (false CONTENT_CHANGED vs TEMPLATE_DRIFT) → make thresholds config; start conservative; log distances for tuning.
- R2 No prior version at rollout (cold start) → everything NEW; acceptable; backfill from Bronze via build_silver + fingerprint script if history exists (see Unresolved #2 in plan.md).
- R3 SimHash inline bug → unit-test hamming on known vectors; keep function small/pure.
- R4 DOM sig instability across benign reorder → use sorted multiset (order-insensitive) not sequence.

## Security Considerations
- Fingerprints derived from untrusted HTML via BeautifulSoup only (no exec). No new network surface.
- Store hex fingerprints only; no raw content copied into version log (points via url_title_hash + sha256).

## Next steps
- Phase 3 catalog uses `state`/`recommendation` + `changed_since` to decide which work-packages are pending re-handoff.
- Agent (Phase 4/5 spec) treats SELECTOR_BROKEN/TEMPLATE_DRIFT packages as skip/hold.
