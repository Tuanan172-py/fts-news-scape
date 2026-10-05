# Phase 01 — Source Verification & Selector Confirmation

## Context Links
- `research/researcher-01-vneconomy-source.md` (Q1 unresolved: content selector)
- `research/researcher-02-codebase-integration.md`
- `scout/scout-01-code-contracts.md`
- Anchor: `src/scrapers/capture_mixin.py` (`_capture_and_extract`, `_density_extract`)

## Overview
- **Date:** 2026-08-17 | **Priority:** Critical (gates all later phases) | **Impl status:** Not started | **Review status:** Not reviewed
- **Description:** Empirically confirm the detail-page `content_selector`, RSS shape, date/author/symbol handling by capturing 2-3 REAL vneconomy detail pages + 1 RSS feed. Selector quality directly determines silver `cleaned_text` quality (bronze is byte-exact, silver derives from it).

## Key Insights
- RSS has NO `content:encoded` → detail-fetch mandatory.
- Detail pages server-rendered; images direct `src` on `premedia.vneconomy.vn` (no lazy-resolve needed).
- CaptureMixin ALWAYS saves raw byte-exact first; selector only affects `content_html` (silver re-derives via trafilatura anyway) — but a good selector improves medium/low fallback + `_looks_complete` validity gate.
- `_density_extract` (readability-lxml / goose3) is the safety net if selector misses.

## Requirements
**Functional**
- Capture 1 real RSS feed → `tests/fixtures/vneconomy_feed.xml` (trim to 2-3 entries, keep XML valid).
- Capture 2-3 real detail pages; pick ONE → `tests/fixtures/vneconomy_detail_page.html` (byte-exact full page).
- Confirm single CSS selector (or comma-list) that isolates article body across all 3 sample pages.
- Verify RSS `link` uses `.htm` article URLs (researcher-01 Q4).

**Non-functional**
- Respect 1s crawl-delay during manual capture (compliance).

## Architecture
Capture is one-off recon (curl/python), not committed code. Selector feeds phase-02 config + phase-03 default. Data flow unchanged: RSS→detail→RawStore(bronze)→SilverBuilder(silver).

## Related Code Files
- CREATE `tests/fixtures/vneconomy_feed.xml`
- CREATE `tests/fixtures/vneconomy_detail_page.html`
- READ-ONLY: `capture_mixin.py`, `rss_generic.py`

## Implementation Steps
1. Fetch feed: `curl -sS -H "User-Agent: Mozilla/5.0" https://vneconomy.vn/chung-khoan.rss -o vneconomy_feed_raw.xml` (respect delay between calls).
2. Extract 2-3 `<item><link>` URLs from feed (`.htm` articles).
3. Fetch each detail page with 1s+ delay: `curl -sS -H "User-Agent: Mozilla/5.0" <url> -o pageN.html`.
4. Inspect body wrapper across pages. Test candidates in priority order:
   - `div.detail__content`
   - `article`
   - `div.article-content, article` (comma fallback)
   Verify: `BeautifulSoup(html,"lxml").select_one(sel).get_text(strip=True)` returns full body, no nav/footer/ads.
5. If no stable class → rely on `article` + density fallback; record decision.
6. Confirm date/author in feed: `published_parsed` present (feedparser parses RFC-2822 GMT); note author string + "K " prefix examples.
7. Trim feed fixture to 2-3 entries (keep at least one with a watchlist symbol in title/summary for ticker test). Save detail fixture byte-exact (`.read_text` UTF-8 must round-trip).
8. Record confirmed selector value for phase-02/03.

## Todo List
- [ ] Capture RSS feed, trim to 2-3 entries → fixture
- [ ] Capture 2-3 detail pages
- [ ] Confirm `content_selector` value (document it)
- [ ] Verify `published_parsed` populated + note author/prefix samples
- [ ] Verify `.htm` link pattern
- [ ] Save `vneconomy_detail_page.html` byte-exact fixture
- [ ] Ensure ≥1 feed entry contains a watchlist ticker (for phase-04)

## Success Criteria
- `content_selector` confirmed on 3 sample pages (single value or comma-list), documented in this file + phase-02.
- `feedparser.parse(_decode_feed(open(fixture,'rb').read())).entries` yields ≥2 entries with non-empty `link`,`title`,`published_parsed`.
- `select_one(selector).get_text(strip=True)` on detail fixture returns article body (non-trivial length).

## Risk Assessment
- **R1:** No stable body class → mitigate with `article` + `_density_extract` (already exists). Acceptable.
- **R2:** Selector varies by section (chung-khoan vs video/eMagazine) → capture across ≥2 sections; comma-list selector.
- **R3:** Fixture too large (full page) → keep as-is (byte-exact required); only feed trimmed.

## Security Considerations
- Honor robots.txt (articles allowed) + 1s crawl-delay during manual capture. No `/api/`, `/tim-kiem.html?`, `?nocache=true` fetches.
- Send realistic User-Agent; low volume (≤4 requests total).

## Next Steps
- Feeds selector → phase-02 config. Fixtures → phase-04 tests. Blocks 02-05.
