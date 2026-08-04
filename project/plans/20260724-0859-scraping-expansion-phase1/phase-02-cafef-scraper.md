# Phase 02 — CafeF Scraper (API) + Domain Skill + Tests

## Context Links
- Parent plan: [plan.md](plan.md)
- Depends on: [phase-01-foundation-refactor.md](phase-01-foundation-refactor.md) (BaseScraper, store v2, config schema)
- Spec: `docs/system-prompt.md` §10 (CafeF example), §13 Sprint 1
- Research: `thamkhao/present/docs_cafef/CafeF.md` (endpoint + params), `thamkhao/present/docs_cafef/OUTPUT_STRUCTURE.md` (raw output schema)
- Framework report: [research/researcher-01-frameworks-report.md](research/researcher-01-frameworks-report.md) (requests sync, trafilatura)

## Overview
- **Date:** 2026-07-24
- **Description:** First concrete `BaseScraper` subclass: CafeF internal JSON API, symbol-driven from watchlist, custom `/Date(ts+tz)/` parsing, detail-page fetch preserving raw HTML from `div#mainContent`. Includes domain skill doc + tests + 100-article quality verification.
- **Priority:** High (validates Phase 1 abstraction; spec Sprint 1 deliverable)
- **Implementation status:** Not started
- **Review status:** Not reviewed

## Key Insights
- CafeF list pages are JS dynamic-loaded (`div#div_data_news` absent in static HTML) → static HTML parse impossible; API is the only sane method (thamkhao/CafeF.md story section).
- Endpoint: `GET https://cafef.vn/du-lieu/Ajax/PageNew/News.ashx?symbol={sym}&pageIndex=1&pageSize=100` — requires `User-Agent` + `Referer: https://cafef.vn/` headers or returns empty/403.
- Spec §10 mentions `symbol` lowercase + `NewsType=0` param; thamkhao docs omit NewsType — verify live, keep param configurable in YAML (unresolved Q4 in plan.md).
- Date format `/Date(1770108462000+0700)/` — ms epoch + tz suffix; regex parse, convert to `Asia/Ho_Chi_Minh` ISO string.
- List API returns metadata only; article body needs detail-page GET → extract `div#mainContent` (raw HTML preserved) + trafilatura for clean text. Detail fetch is the expensive part: 3s rate limit × N new articles — cap per-cycle detail fetches (config `max_details_per_cycle: 30`).
- pageSize max 200 per spec; use 100 (thamkhao-proven).

## Requirements
1. `CafeFScraper(BaseScraper)` — zero orchestrator/core edits (config-driven proof).
2. Iterate watchlist symbols from `config/watchlist.yaml`; dedup before detail fetch (never fetch detail for known article).
3. Store: `content_html` = raw `div#mainContent` outerHTML; `content_text` = trafilatura extract; `symbols` = queried symbol; `published_at` parsed VN timezone.
4. Rate limit ≥3s to cafef.vn (list + detail share one domain bucket — HTTPClient already per-domain).
5. Domain skill doc: method, endpoint, params, pitfalls (mirrors spec §10 table).
6. Tests: happy path with fixture JSON + edge cases (bad date, empty response, detail 404).
7. Verify 100 real articles: ≥95% have title+body+date.

## Architecture
```
src/scrapers/__init__.py
src/scrapers/cafef.py          # CafeFScraper(BaseScraper)
config/domains/cafef.yaml
docs/skills/cafef.md
tests/fixtures/cafef_list_response.json
tests/fixtures/cafef_detail_page.html
tests/test_cafef.py
```
**config/domains/cafef.yaml:**
```yaml
name: cafef
enabled: true
method: api
rate_limit: 3.0
timeout: 30
api:
  endpoint: "https://cafef.vn/du-lieu/Ajax/PageNew/News.ashx"
  http_method: GET
  params: {pageIndex: 1, pageSize: 100}     # symbol injected per watchlist item
  headers: {Referer: "https://cafef.vn/"}   # UA from HTTPClient rotation
detail:
  content_selector: "div#mainContent"
  max_details_per_cycle: 30
pitfalls: "JS dynamic list pages; /Date(ms+tz)/ format; symbol lowercase; needs Referer"
```
**Flow:** `fetch_list()` → loop watchlist symbols → GET per symbol → concat JSON items (tag each with symbol) | `parse_item()` → Article(url, title, summary, published_at via `parse_cafef_date()`) | `enrich()` → GET detail URL → BS4 select `div#mainContent` → `content_html`; `trafilatura.extract(html)` → `content_text`; fallback: selector miss → trafilatura on full page for text, full page HTML as raw (log WARN).

## Related Code Files
**Create:** `src/scrapers/__init__.py`, `src/scrapers/cafef.py`, `config/domains/cafef.yaml`, `docs/skills/cafef.md`, `tests/test_cafef.py`, `tests/fixtures/cafef_list_response.json`, `tests/fixtures/cafef_detail_page.html`, `scripts/verify_quality.py` (reusable quality checker)
**Modify:** `config/watchlist.yaml` (seed ~20 liquid tickers: FPT, HPG, VIC, VHM, VNM, SSI, VND, HCM, VCI, MWG, MBB, TCB, VCB, STB, GAS, POW, DGC, PNJ, REE, VJC)
**Delete:** none

## Implementation Steps
1. Capture real fixture: one manual `curl`/requests call `?symbol=fpt&pageIndex=1&pageSize=5` → save JSON to `tests/fixtures/cafef_list_response.json`; save one detail page HTML. Confirm actual JSON field names (Title/Link/PublishDate etc.) — thamkhao OUTPUT_STRUCTURE.md is reference; verify `NewsType` param necessity here.
2. Write `parse_cafef_date(raw: str) -> str`:
   ```python
   m = re.search(r"/Date\((\d+)([+-]\d{4})?\)/", raw)
   dt = datetime.fromtimestamp(int(m.group(1)) / 1000, tz=ZoneInfo("Asia/Ho_Chi_Minh"))
   return dt.isoformat()   # None + WARN log on no-match
   ```
3. Implement `CafeFScraper.fetch_list()`: for each watchlist symbol (lowercased): `self.http.get_json(endpoint, params={**cfg_params, "symbol": sym}, referer=...)`; on None/invalid JSON → log ERROR, continue next symbol (one symbol failing must not kill cycle); attach `{"_symbol": sym}` to each item.
4. Implement `parse_item()`: map JSON fields → Article; absolute URL (join `https://cafef.vn` if relative); skip + WARN on missing url/title.
5. Implement `enrich()` with per-cycle cap: counter in scraper instance; beyond `max_details_per_cycle` → keep summary as content_text, mark `metadata_json["detail_deferred"] = true` (next cycle re-attempt not needed Phase 1 — dedup already stored; acceptable per incremental delivery, note in skill doc).
6. Selector extract: `BeautifulSoup(html, "lxml").select_one(cfg["detail"]["content_selector"])` → `str(node)` as content_html; `trafilatura.extract(str(node), include_comments=False)` as content_text; verify Vietnamese diacritics survive (encoding: resp.encoding = 'utf-8' if misdetected).
7. Write `docs/skills/cafef.md`: table format from spec §10 — domain, method, endpoint, headers, params, date format, content selector, pitfalls, sample response snippet.
8. Tests (`tests/test_cafef.py`, mock HTTPClient):
   - happy: fixture list → N Articles, correct date ISO + tz +07:00
   - edge: `/Date(...)/ ` malformed → published_at None, no crash
   - edge: empty JSON list → ScrapeResult.fetched == 0, no errors raised
   - edge: detail 404 → article kept with summary body, error logged
   - dedup: second run same fixture → new == 0
9. Write `scripts/verify_quality.py`: query articles where source_domain='cafef.vn' → % with title+content_text(len>200)+published_at; print report.
10. Live run: `python scripts/run_once.py cafef` with 20-symbol watchlist until ≥100 articles stored; run verify_quality → require ≥95%.

## Todo List
- [ ] Capture live fixtures (list JSON + detail HTML); confirm field names + NewsType
- [ ] parse_cafef_date() + unit tests
- [ ] CafeFScraper.fetch_list / parse_item / enrich
- [ ] Detail cap + fallback extraction path
- [ ] config/domains/cafef.yaml + watchlist seed
- [ ] docs/skills/cafef.md
- [ ] tests/test_cafef.py (5 cases) green
- [ ] scripts/verify_quality.py
- [ ] Live 100-article run ≥95% quality

## Success Criteria
- 100 CafeF articles in DB; ≥95% have title + content_text + published_at (VN tz).
- Raw HTML preserved: `content_html` contains original tags/tables from `div#mainContent`.
- Re-run produces 0 duplicates. One failing symbol doesn't abort cycle.
- No modification to `core/` or orchestrator needed — proves 30-min-add-domain pattern.

## Risk Assessment
- **API param/field drift since thamkhao research (Feb 2026):** step 1 live fixture capture de-risks before coding.
- **Anti-bot tightening (403 on burst):** 3s rate limit + Referer + UA rotation; if blocked → reduce pageSize, add jitter 3–5s.
- **Detail fetch volume:** 20 symbols × new articles can exceed cycle budget → `max_details_per_cycle` cap; monitor cycle duration in Phase 4 metrics.
- **`div#mainContent` layout change:** fallback trafilatura full-page path keeps text quality; WARN alerts via Phase 4 monitoring.

## Security Considerations
- No auth/credentials for CafeF. Respect rate limits (≥3s) — politeness is the anti-ban control.
- Sanitize nothing away from raw HTML (spec: preserve), but never render stored HTML anywhere without escaping (note for future dashboard).

## Next Steps
Phase 3 — replicate pattern for Vietstock (POST), TNCK (zone), FireAnt (bearer). Phase 4 can start in parallel (depends only on Phase 1).
