# Plan — RAW HTML CAPTURE (Vietstock + CafeF)

**Created:** 2026-08-13 · **Owner:** ingestion · **Status:** PLANNED — APPROVED (0/6 phases done; all open questions resolved)

## Goal
Capture FULL raw HTML of each selected Vietstock + CafeF article as an independently-inspectable
on-disk artifact BEFORE any cleaning. Preserve everything as-is (text, headings, lists, tables,
captions, all `<img>` + lazy attrs, video/iframe/embeds, links, author/time/category). Record
capture status + failure metadata explicitly. Reuse `enrich()` + `HTTPClient`, honor rate limits /
robots.txt. NO trafilatura/normalization in capture phase.

## Approach (KISS/DRY)
Both sources are **~90% server-rendered** → `requests` via existing `HTTPClient.get_response()`
suffices for the vast majority. Add ONE shared `RawStore` writer (disk: `.html` + `.meta.json`
sidecar). Wire it into each scraper's `enrich()` as the FIRST step (raw save), THEN existing
parse/clean continues unchanged downstream. Capture metadata lives in `Article.metadata["capture"]`
(zero DB schema churn — chosen over new columns/BLOB; justified in phase-01).
**Fallback is CONTENT-BASED, not static per-domain** (D1): after each HTTP GET, run a cheap
`_looks_complete(html, container_selector)` validity check (body byte-size threshold, main container
present/non-empty, no known "empty-render"/error markers). Only pages that FAIL the check (~5–10%:
Infographic/E-Magazine) escalate to the OPTIONAL Playwright fallback. Do NOT pre-decide "this domain
needs JS." Playwright stays deferred/optional, gated on phase-06 evidence.

## Design decisions (locked)
- Storage: disk artifact `data/raw_html/<domain>/<yyyymmdd>/<url_title_hash>.html` + `.meta.json`.
  NOT SQLite BLOB (keeps DB small, artifacts grep-able/offline-inspectable, git-ignorable).
- Metadata: `Article.metadata["capture"]` dict (path, sha256, http_status, headers subset, fetch_ts,
  render_method, capture_status, missing[], error). No `store.py` schema change in v1.
- Vietstock: build DEDICATED `src/scrapers/vietstock.py` (container-accurate full-page capture +
  metadata) replacing generic-RSS path. Justified in phase-03.
- CafeF: extend `enrich()` to save FULL page raw first; keep `#mainContent` as a captured sub-region
  reference (`content_html`), not the raw artifact.
- Reuse rate limiter/retry/UA — never bypass. robots.txt check added centrally (phase-04).
- **Image manifest, not HTML mutation** (D2): AC5 (image identifying info + URL) satisfied by a
  READ-ONLY `images[]` array in `.meta.json`, built by scanning the byte-exact raw HTML (BeautifulSoup,
  read-only). Records `{outer_tag, resolved_url, alt, title, caption}` per `<img>`. `resolved_url` =
  first present of `src, data-src, data-original, original-src, document-path, data-lazy`, else first
  URL in `srcset`. `<figure>/<figcaption>` paired for caption. The `data-src→src` SWAP itself is a
  DOWNSTREAM parser concern, NEVER this capture phase — raw `.html` stays byte-exact.
- **WARC rejected** (D3): keep plain `.html` + `.meta.json`. WARC bloats storage 5–10x and complicates
  the NLP read pipeline; quant use needs only text+metadata, not full-resource replay.
- **Parser resilience via text-density fallback** (D5): when the primary container selector returns
  empty/missing, `content_html` falls back to a text-density extractor (`readability-lxml`/`goose3`,
  ~95% news accuracy). This affects ONLY the parsed `content_html` sub-region — NEVER the raw `.html`
  artifact (always saved first, byte-exact). Because raw is saved first, a broken parser can be fixed
  and re-run OFFLINE over stored artifacts without re-hitting the site (DOM-mutation/layout-shift
  resilience). See phase-02/03.
- **Rate limiting = hard limit + adaptive backoff + optional proxy** (D4): keep token-bucket hard limit
  (~3 req/s / existing per-domain 3.0s); ADD source-level pause + exponential backoff (2→4→8→16s) on
  429/503; optional config-gated proxy rotation. EXTENDS existing `HTTPClient` Retry + `RateLimiter`
  (does not rebuild). See phase-04.

## Phases
| # | Phase | File | Status | Progress |
|---|-------|------|--------|----------|
| 01 | Raw artifact store + capture metadata schema | [phase-01-raw-store-and-metadata.md](phase-01-raw-store-and-metadata.md) | ✅ DONE | 100% |
| 02 | CafeF full-raw capture | [phase-02-cafef-full-raw-capture.md](phase-02-cafef-full-raw-capture.md) | ✅ DONE | 100% |
| 03 | Vietstock dedicated scraper + full-raw capture | [phase-03-vietstock-dedicated-scraper.md](phase-03-vietstock-dedicated-scraper.md) | ✅ DONE | 100% |
| 04 | robots.txt compliance + rate-limit hardening | [phase-04-robots-and-rate-limit.md](phase-04-robots-and-rate-limit.md) | ✅ DONE | 100% |
| 05 | [DEFERRED/OPTIONAL] Playwright fallback | [phase-05-playwright-fallback-optional.md](phase-05-playwright-fallback-optional.md) | ⏸ DEFERRED | 0% |
| 06 | Tests + acceptance verification | [phase-06-tests-and-acceptance.md](phase-06-tests-and-acceptance.md) | ✅ DONE | 100% |

**Implementation status (2026-08-13):** Phases 01–04 + 06 implemented & verified. New tests green
(`test_raw_store/backoff/robots/looks_complete/cafef_capture/vietstock` + updated `test_cafef`).
LIVE E2E validated (`scripts/validate_capture.py`): CafeF + Vietstock raw artifacts sha256 byte-exact,
capture_status=ok, images[] with real URLs. Docs: `project/docs/design/06-raw-html-capture.md`.
2 unrelated pre-existing failures remain (`test_monitor_notify` emoji vs `[+]` — code/test drift, NOT in this diff).

## Dependencies / order
01 → (02, 03) → 04 → 06. 05 optional, independent, only if edge cases appear in 06.

## Acceptance → phase map
- AC1 exact URL · AC2 full raw · AC3 preserve all → phase-02/03 (store from 01)
- AC5 image info → phase-01 read-only `images[]` manifest (D2); wired phase-02/03; asserted phase-06
- AC4 dynamic/lazy → phase-02/03 static (~90%) + `_looks_complete` validity check (D1); phase-05
  (hardened Playwright) only for ~5–10% incomplete edge cases
- AC6 offline-inspectable · AC7 no-clean → phase-01 (disk sidecar; raw save precedes any parse)
- AC8 failure metadata → phase-01 schema + phase-02/03 wiring
- AC9 rate/robots/ToS → phase-04

## Context inputs
- research/researcher-01-source-structure.md · research/researcher-02-capture-architecture.md
- scout/scout-01-codebase.md · project/docs/dev/03-adding-a-source.md

## Unresolved questions

### Stakeholder decisions — RESOLVED (folded in 2026-08-13)
- **D1** Content-based fallback trigger (`_looks_complete` check, not static per-domain) → RESOLVED:
  plan Approach + phase-02/03 (validity check) + phase-05 (trigger).
- **D2** Read-only `images[]` manifest in meta.json (no HTML mutation) → RESOLVED: phase-01 schema +
  phase-02/03 wiring + phase-06 assertion.
- **D3** WARC rejected, keep `.html` + `.meta.json` → RESOLVED: plan Design decisions.
- **D4** Token-bucket hard limit + adaptive exp backoff + optional proxy rotation → RESOLVED: phase-04.
- **D5** Parser text-density fallback (`content_html` only, raw untouched) → RESOLVED: phase-02/03.
- **D6** Playwright hardening (stealth, async, residential proxy) → RESOLVED: phase-05 (deferred).

### Owner decisions — RESOLVED (2026-08-13)
- **Q1** Detail cap → **Cap + backfill sweep**: keep ~30/cycle steady-state; deferred articles queued
  and raw-captured by a separate `backfill` pass (eventual full coverage, bounded cycle). (phase-02/03)
- **Q2** Retention → **Keep all + gitignore**: retain `data/raw_html/` indefinitely, exclude from git;
  revisit rotation if disk grows. (phase-01 adds `.gitignore`)
- **Q3** robots gate → **Scraper-base opt-in**: `RobotsGate` used by scrapers per-source; does not alter
  the other 20+ domains. (phase-04)
- **Q4** Source of truth → conventions sourced from `docs/dev/03-adding-a-source.md` + code
  (`development-rules.md` referenced by workflow does not exist in repo). DEFAULT ACCEPTED.
- **Q5** meta.json headers → **Subset whitelist**: content-type, content-length, last-modified, etag,
  server, date; drop Set-Cookie/Authorization. (phase-01)

## Revision log
### 2026-08-13 — stakeholder feedback folded in (D1–D6)
- **D1** Fallback trigger made CONTENT-based (`_looks_complete` validity check post-HTTP), not static
  per-domain → Approach, phase-02/03, phase-05.
- **D2** AC5 met via read-only `images[]` manifest in meta.json (byte-exact raw HTML preserved; the
  `data-src→src` swap is downstream, not capture) → phase-01 schema, phase-02/03, phase-06.
- **D3** WARC explicitly rejected (storage bloat 5–10x, complicates NLP read) → Design decisions.
- **D4** Rate-limit EXTENDED: hard limit + source-level pause + exp backoff (2→4→8→16s) + optional
  proxy hook; reuses existing Retry/RateLimiter → phase-04.
- **D5** Parser text-density fallback for `content_html` sub-region ONLY (raw artifact never mutated;
  re-runnable offline) → phase-02/03.
- **D6** Playwright fallback hardened (stealth/undetected, async_playwright, residential proxy);
  remains DEFERRED/OPTIONAL, evidence-gated on phase-06 → phase-05.
