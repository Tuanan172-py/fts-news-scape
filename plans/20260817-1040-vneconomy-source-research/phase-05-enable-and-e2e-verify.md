# Phase 05 — Enable + End-to-End Bronze→Silver Verify + Quality Gate

## Context Links
- `scripts/run_once.py` (delegates to `orchestrator.main(["--once", "vneconomy"])`)
- `src/pipeline/silver_builder.py` (offline, domain-agnostic, unchanged)
- `schemas/silver-v1.schema.json` (required: cleaned_text minLength 1)
- Depends: phases 02-04 complete

## Overview
- **Date:** 2026-08-17 | **Priority:** High | **Impl status:** Not started | **Review status:** Not reviewed
- **Description:** Live single-cycle run; verify bronze raw_html persisted byte-exact AND silver JSON derived with non-empty `cleaned_text`. Confirm parity with cafef/vietstock output.

## Key Insights
- `enabled: true` (phase-02) makes orchestrator auto-include vneconomy; `run_once.py vneconomy` runs just this domain.
- Bronze written by CaptureMixin during enrich → `data/raw_html/vneconomy.vn/<YYYYMMDD>/...`.
- Silver derived offline by SilverBuilder → `data/silver/vneconomy.vn/<YYYYMMDD>/<article_id>.json` (partition mirrors bronze). Confirm how silver derive is triggered (same path cafef/vietstock use — check orchestrator/derive step or run the derive script).
- Quality: `cleaned_text` non-empty required (schema `minLength:1`); good selector → `extraction_quality: high|medium`.

## Requirements
**Functional**
- `python scripts/run_once.py vneconomy` completes; bronze raw_html files created (byte-exact, `.meta.json` sidecar).
- Silver JSON produced for ≥1 article with non-empty `cleaned_text`, valid vs `silver-v1.schema.json`.
- Crawl-delay honored (1s) at runtime via RobotsGate.

**Non-functional**
- No exceptions raised (never-raise contract); errors only in `ScrapeResult.errors`.

## Architecture
```
run_once.py vneconomy → orchestrator run_cycle → VnEconomyScraper.run
  → bronze RawStore.save (data/raw_html/vneconomy.vn/...)
  → DBWriter dedup/insert
[derive] SilverBuilder.build(meta, raw_bytes) → data/silver/vneconomy.vn/.../<id>.json
```

## Related Code Files
- RUN `scripts/run_once.py`
- VERIFY outputs under `data/raw_html/vneconomy.vn/`, `data/silver/vneconomy.vn/`
- READ-ONLY `src/pipeline/silver_builder.py`, `schemas/silver-v1.schema.json`

## Implementation Steps
1. `python scripts/run_once.py vneconomy` (dev env; live network — respects robots/crawl-delay).
2. Confirm bronze: list `data/raw_html/vneconomy.vn/<YYYYMMDD>/` → `.html` + `.meta.json` present; spot-check one `.html` is full page (byte-exact vs live).
3. Trigger/confirm silver derive (same mechanism as cafef/vietstock — identify derive entrypoint; run it if separate from run_once).
4. Confirm silver: open a `data/silver/vneconomy.vn/.../<id>.json` → `cleaned_text` non-empty; `domain=="vneconomy.vn"`; `content_sha256` present; `extraction_quality` in {high,medium} (low/empty = selector regression → revisit phase-01).
5. Validate against schema (jsonschema) if validator available.
6. Re-run once more → idempotent/dedup (no dup silver; `built_at=meta.fetch_ts` stable).
7. Compare a vneconomy silver record shape to a vietstock one → parity.
8. Full `pytest -q` final regression gate.

## Todo List
- [ ] run_once.py vneconomy completes no exception
- [ ] bronze raw_html + .meta.json present, byte-exact
- [ ] silver JSON produced, cleaned_text non-empty
- [ ] extraction_quality high|medium (not empty/low)
- [ ] schema-valid silver record
- [ ] dedup idempotent on re-run
- [ ] parity vs vietstock silver shape
- [ ] full pytest green

## Success Criteria
- Bronze raw_html byte-exact + silver JSON with non-empty `cleaned_text` for ≥1 vneconomy article.
- `extraction_quality` ≥ medium.
- All tests pass. Parity with cafef/vietstock confirmed.

## Risk Assessment
- **R1:** `cleaned_text` empty → selector/density failed → revisit phase-01 selector; trafilatura in silver is domain-agnostic and usually recovers (primary silver path is trafilatura on raw, not scraper `content_html`).
- **R2:** Silver derive not auto-triggered by run_once → locate + run derive step explicitly (document command).
- **R3:** Live site change vs fixtures → bronze still byte-exact; only content_html/quality affected.
- **R4:** Rate/crawl-delay → single cycle, ≤30 details, 1s delay honored.

## Security Considerations
- `respect_robots: true` enforced live; 1s crawl-delay honored (RobotsGate). Only article URLs fetched (no `/api/`, `/tim-kiem.html?`, `?nocache=true`). Backoff on 429/503. Low volume single cycle.

## Next Steps
- Commit (git-manager) when user requests. Optionally add vneconomy to any scheduled cycle / README source list.
- If quality < medium: iterate selector (phase-01) then re-run phase-05.
