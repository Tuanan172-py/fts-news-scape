# Plan — Add VnEconomy (vneconomy.vn) as 3rd bronze→silver source

**Date:** 2026-08-17 | **Owner:** planner | **Status:** ✅ Implemented & verified (2026-08-17)

## Goal
Add `vneconomy.vn` as fully-implemented bronze→silver scraper at parity with cafef + vietstock.
Pattern: dedicated `VnEconomyScraper(CaptureMixin, BaseScraper)` mirroring `vietstock.py`.
RSS list → detail-fetch → RawStore byte-exact bronze → offline SilverBuilder derives silver (zero silver change).

## Net delta (verified — do not re-derive)
- CREATE `src/scrapers/vneconomy.py` (~55 lines, mirror vietstock)
- CREATE `tests/test_vneconomy.py`, `tests/fixtures/vneconomy_feed.xml`, `tests/fixtures/vneconomy_detail_page.html`
- MODIFY `src/scrapers/__init__.py` (add `vneconomy` to import tuple)
- MODIFY `config/domains/vneconomy.yaml` (method→vneconomy, enabled→true, add capture/compliance/content_selector/language)
- ZERO orchestrator / pipeline / silver_builder / models changes

## Key open risk
Exact CSS `content_selector` for detail body NOT confirmed (researcher-01 Q1: "semantic HTML, no obvious wrapper"). Phase-01 empirically confirms via 2-3 live pages before writing scraper. `_density_extract` (readability/goose3) fallback exists in CaptureMixin as safety net → bronze always saved byte-exact regardless.

## Phases
| # | Phase | File | Priority | Status |
|---|-------|------|----------|--------|
| 01 | Source verification + selector confirmation | phase-01-source-verification-and-selector.md | Critical | ✅ Done — selector `#article-editor` |
| 02 | Config update (vneconomy.yaml) | phase-02-config-update.md | High | ✅ Done |
| 03 | Dedicated scraper implementation | phase-03-scraper-implementation.md | High | ✅ Done |
| 04 | Tests (mirror test_vietstock pattern) | phase-04-tests.md | High | ✅ Done — 4/4 pass |
| 05 | Enable + end-to-end bronze→silver verify | phase-05-enable-and-e2e-verify.md | High | ✅ Done — 30 bronze→30 silver (all `high`) |

## Verification results (2026-08-17)
- Env: recreated `.venv` (Python 3.14.3; old venv was empty — OneDrive sync loss) + installed `requirements.txt` + pytest.
- Phase-01: `content_selector = #article-editor` (a `<main>`, stable across 3 sections, precedes `<article>` in DOM). Author RSS-clean ("Kim Phong", no "K " prefix → cleanup skipped, YAGNI). Fixtures: `vneconomy_capture_feed.xml` (3 items, one w/ TCB), `vneconomy_detail_page.html` (byte-exact).
- Tests: `tests/test_vneconomy.py` 4/4 pass; regressed `test_rss_scraper::test_vneconomy_feed_real_fixture` (I had clobbered shared `vneconomy_feed.xml`) → fixed by renaming my fixture; now passes.
- E2E: `run_once.py vneconomy` → 150 new, 30 details, exit 0, no exceptions. `rederive_from_bronze.py vneconomy.vn` → 30 processed, 30 schema-ok, 0 held. All 30 silver `extraction_quality: high`, non-empty `cleaned_text`, `domain: vneconomy.vn`.
- Pre-existing (NOT mine): `test_monitor_notify.py` 2 failures — notifier emits `[+]/[~]/[-]` but test expects emoji `🟢`; untouched by this work.

## Dependencies (linear)
01 (confirm selector + capture fixtures) → 02 (config uses selector) → 03 (scraper) → 04 (tests use fixtures) → 05 (e2e).

## Established facts (context)
- RSS: 3 feeds live (chung-khoan/tai-chinh/thi-truong), 50 items each, NO `content:encoded` → MUST detail-fetch.
- pubDate: RFC-2822 GMT → feedparser `published_parsed` (UTC) → VN ISO via `_parse_entry_date` (reuse, DRY).
- Detail date text: "HH:MM, DD/MM/YYYY" (only needed if RSS pubDate missing; not used in bronze path — silver derives from raw).
- Author: text, sometimes noisy "K " prefix.
- No structured tickers → `tag_tickers(title+summary, watchlist)`.
- Images: direct `src` on `premedia.vneconomy.vn` CDN (no lazy-load).
- robots.txt: articles allowed, 1s crawl-delay → `compliance.respect_robots: true` (RobotsGate honors crawl-delay).
- Server-rendered, no anti-bot.

## Input reports
- `research/researcher-01-vneconomy-source.md` — source recon
- `research/researcher-02-codebase-integration.md` — integration map
- `scout/scout-01-code-contracts.md` — exact code contracts (most authoritative)

## Contract anchors (read verbatim)
- `src/scrapers/vietstock.py` — parity target (copy structure)
- `src/scrapers/capture_mixin.py` — `_init_capture` / `_capture_and_extract`
- `src/scrapers/rss_generic.py` — reuse `_clean_title/_decode_feed/_parse_entry_date`
- `tests/test_vietstock.py` + `tests/_fakes.py::FakeHTTP` — test pattern
- `config/domains/vietstock.yaml` — config parity template

## Success criteria (whole plan)
- `python scripts/run_once.py vneconomy` → bronze raw_html (byte-exact) + silver JSON with non-empty `cleaned_text`.
- `pytest tests/test_vneconomy.py` green; `vneconomy` registered in REGISTRY.
- No regressions: full `pytest` green.

## Unresolved questions
1. `content_selector` exact value — resolved empirically in phase-01 (candidates: `div.detail__content`, `article`, density fallback).
2. Author "K " prefix — cosmetic; silver derives author from raw, scraper stores RSS author as-is. Cleanup optional (phase-03 note). Confirm whether pipeline consumes `article.author` downstream (likely not for silver).
3. `./docs/development-rules.md` referenced by global rules does NOT exist in repo — proceeding on existing code conventions (Vietnamese docstrings, existing patterns). Confirm no external rules file expected.
4. Article URL `.htm` pattern from RSS — verify in phase-01 fixture capture (assume RSS `link` authoritative).
