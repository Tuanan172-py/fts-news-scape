# Phase 03 — API Scrapers: TNCK, FireAnt

> **SCOPE CHANGE 2026-07-24 (verified — see `reports/01-verification-report.md`):** Vietstock internal API unreachable via HTTP client (endpoints hidden in JS bundles; all probed paths soft-404). Pre-approved fallback executed: **Vietstock → RSS, moved to Phase 5**. This phase = TNCK + FireAnt only. Verified live: TNCK API works (gzip; date field = `date` not `date_unix`; ⚠️ `phrase` param appeared ignored — validate with fixtures, fallback = no-phrase pass + client-side ticker tagging). FireAnt endpoint alive, 401 without token as expected. CafeF (Phase 2) needs `Type=1` param.

## Context Links
- Parent plan: [plan.md](plan.md)
- Depends on: [phase-02-cafef-scraper.md](phase-02-cafef-scraper.md) (proven BaseScraper pattern), Phase 1 abstractions
- Spec: `docs/system-prompt.md` §8, §13 Sprint 2
- Research: `thamkhao/present/docs_vietstock/Mô tả.md` + `Discovered Channels.md` (38 working endpoints, channel IDs), `thamkhao/present/docs_tnck/Mô tả endpoint api.md` (zone API + output schema), `thamkhao/present/docs_fireant/FireAnt.md` + `FIREANT_OUTPUT_JSON.md` (bearer auth, 2-step fetch), `thamkhao/present/Tổng hợp/So sánh.md` (4-system comparison)

## Overview
- **Date:** 2026-07-24
- **Description:** Three more `BaseScraper` subclasses: Vietstock (POST internal API, channel-based, no symbol filter), TNCK (GET zone API with server-side `phrase` ticker filter), FireAnt (REST, Bearer token, list+detail 2-step). Each: YAML config + module + skill doc + tests. Brings domain count to 4.
- **Priority:** High (core of "quantity" metric — spec Sprint 2)
- **Implementation status:** Not started
- **Review status:** Not reviewed

## Key Insights
- **Vietstock:** internal API, POST, returns JSON or HTML partials per endpoint. Confirmed working: `TopPageArticle` (channel 733 = Doanh nghiệp), `NewsMoinhat` (GET, `item` param), `MostViewedArticle`, `Notifi` (breaking, no channel). **No symbol filter param** → filter client-side: regex ticker match (`\b[A-Z]{3}\b` ∩ watchlist) on title+summary, store matches in `symbols`, but keep non-matching market/macro news too (spec scope includes vĩ mô/chính trị). Full URL paths + POST bodies (incl. possible `__RequestVerificationToken`) not in thamkhao docs → DevTools verification step required first.
- **TNCK:** `GET https://api.tinnhanhchungkhoan.vn/api/morenews-zone-{zone}-{page}.html?phrase={TICKER}`, zone 4 = Thông tin doanh nghiệp default. Response `data.contents[]` flatten; fields already clean: `content_id`, `title`, `description`, `date_unix`, `full_url`, `zone_name`, `related_tickers` (comma list — free symbol tagging, better than regex). Needs real-browser UA + `Referer: https://www.tinnhanhchungkhoan.vn/` + `Accept: application/json`.
- **FireAnt:** strict auth `Authorization: Bearer <token>` (from `config/secrets.yaml`, key `fireant_token`); list `GET https://restv2.fireant.vn/posts?symbol={S}&type=1&page=1&pageSize=20` returns empty body field → detail `GET https://restv2.fireant.vn/post/{postID}` for full HTML content. 401/403 → token expired: disable scraper for cycle + ERROR log (Phase 4 notify picks up); no auto-refresh Phase 1.
- All three reuse CafeF patterns: watchlist loop (TNCK/FireAnt), per-cycle detail cap (FireAnt), epoch date parse (TNCK `date_unix`), graceful per-item error handling.
- Combined with CafeF + RSS (Phase 5) → ≥5 domains target.

## Requirements
1. Three scrapers, each config-driven (YAML), zero core edits.
2. Vietstock: ≥2 endpoints (TopPageArticle ch.733 + NewsMoinhat) merged, client-side ticker tagging.
3. TNCK: watchlist iteration via `phrase`; also 1 pass zone-4 without phrase for general corporate news; use `related_tickers` for `symbols` field.
4. FireAnt: token from secrets, 2-step fetch, detail cap, 401/403 self-disable.
5. Per-domain skill docs (`docs/skills/vietstock.md`, `tnck.md`, `fireant.md`).
6. Tests per scraper: happy + ≥1 edge each (spec §12 test rule).
7. Rate limit 3s per domain enforced by shared HTTPClient (each domain independent bucket → 3 scrapers interleave fine sequentially).

## Architecture
```
src/scrapers/vietstock.py   # VietstockScraper(BaseScraper)
src/scrapers/tnck.py        # TnckScraper(BaseScraper)
src/scrapers/fireant.py     # FireAntScraper(BaseScraper)
config/domains/vietstock.yaml, tnck.yaml, fireant.yaml
docs/skills/vietstock.md, tnck.md, fireant.md
tests/test_vietstock.py, test_tnck.py, test_fireant.py (+ fixtures/)
```
**vietstock.yaml sketch:**
```yaml
name: vietstock
method: api
rate_limit: 3.0
api:
  endpoints:                      # multi-endpoint list — scraper iterates
    - {name: TopPageArticle, url: "<VERIFY via DevTools>", http_method: POST,
       body: {channelID: 733, page: 1, pageSize: 20}}
    - {name: NewsMoinhat, url: "<VERIFY>", http_method: GET, params: {item: 20}}
  headers: {Referer: "https://vietstock.vn/", X-Requested-With: XMLHttpRequest}
ticker_tagging: client_regex      # match watchlist tickers in title/summary
pitfalls: "Internal API; no symbol param; some endpoints return HTML partials not JSON; possible anti-CSRF token in POST"
```
**fireant.yaml sketch:**
```yaml
name: fireant
method: api
auth: {type: bearer, secret_key: fireant_token}
api:
  list: {url: "https://restv2.fireant.vn/posts", params: {type: 1, page: 1, pageSize: 20}}
  detail: {url_template: "https://restv2.fireant.vn/post/{post_id}"}
detail: {max_details_per_cycle: 30}
pitfalls: "Token expires → 401/403; list API returns empty body; date field ISO in list response"
```
**tnck.yaml sketch:**
```yaml
name: tnck
method: api
api:
  url_template: "https://api.tinnhanhchungkhoan.vn/api/morenews-zone-{zone}-{page}.html"
  zones: [4]                 # 4 = Thông tin doanh nghiệp
  pages_per_cycle: 2
  headers: {Referer: "https://www.tinnhanhchungkhoan.vn/", Accept: "application/json, text/plain, */*"}
watchlist_phrase: true       # iterate phrase={TICKER} + one no-phrase pass
pitfalls: "date_unix epoch seconds; full content needs detail page fetch (trafilatura); zone IDs per docs_tnck/Khám phá parameter.md"
```

## Related Code Files
**Create:** `src/scrapers/vietstock.py`, `src/scrapers/tnck.py`, `src/scrapers/fireant.py`, 3× `config/domains/*.yaml`, 3× `docs/skills/*.md`, 3× `tests/test_*.py` + fixtures, `src/core/tickers.py` (shared `tag_tickers(text, watchlist) -> list[str]` regex util — used by Vietstock + Phase 5 RSS)
**Modify:** `config/secrets.yaml.example` (add `fireant_token: "PASTE_BEARER_TOKEN"`), `config/watchlist.yaml` (confirm coverage)
**Delete:** none

## Implementation Steps
1. **Vietstock endpoint verification (blocker-first):** open vietstock.vn with DevTools → Network → Fetch/XHR; record exact URLs, POST bodies, required cookies/tokens for `TopPageArticle` + `NewsMoinhat`; save raw responses as fixtures. If POST needs per-session anti-CSRF token → add pre-flight GET homepage to harvest token (document in skill file). If cost too high → fall back to Vietstock RSS (`https://vietstock.vn/rss`, confirmed active in researcher-02 §5) and note method switch in yaml (`method: rss`) — decision point, log in plan review.
2. `src/core/tickers.py`: `tag_tickers(text, watchlist)`: uppercase word-boundary match of 3-char codes against watchlist set; unit test (avoid false positives like "GDP", "CEO" — maintain small stoplist).
3. **VietstockScraper:** `fetch_list()` iterates configured endpoints (POST via `http.post_json`); handle both JSON list and HTML-partial responses (BS4 parse `<a>` title/href for HTML type endpoints — only if needed; prefer JSON endpoints). `parse_item()` → Article; `symbols = tag_tickers(title + summary)`. `enrich()`: detail page fetch + trafilatura (same pattern/cap as CafeF).
4. **TnckScraper:** `fetch_list()`: for zone in zones, for page in 1..pages_per_cycle: no-phrase pass; then per watchlist ticker `phrase={T}` page 1 only. Flatten `raw_json.data.contents`. `parse_item()`: `published_at = datetime.fromtimestamp(item["date_unix"], ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()`; `symbols = item["related_tickers"].split(",")`; url = `full_url`. `enrich()`: fetch `full_url` → trafilatura text + raw HTML (store `<article>`/full page).
5. **FireAntScraper:** `__init__` loads token via `config.load_secrets()["fireant_token"]`; missing token → scraper disabled at construction (WARN, not crash). `fetch_list()`: per watchlist symbol GET /posts; on 401/403 → set `self.errors`, `self.disabled = True`, return [] (stop hammering). `parse_item()` from list JSON (see FIREANT_OUTPUT_JSON.md field names — verify with fixture). `enrich()`: GET `/post/{postID}` → merge `content` field → content_html; trafilatura → content_text; cap 30/cycle.
6. Skill docs: per-domain table (endpoint, method, auth, params, date format, pitfalls, sample curl).
7. Tests (mocked HTTPClient + fixtures):
   - vietstock: happy JSON parse; edge: HTML-partial response handled/skipped without crash
   - tnck: happy flatten + date_unix parse; edge: empty `data.contents`; related_tickers empty string
   - fireant: happy 2-step merge; edge: 401 → disabled, no retry storm, run() returns errors list
8. Live smoke: `python scripts/run_once.py vietstock tnck fireant`; run `scripts/verify_quality.py` per domain ≥95%.
9. Measure full-cycle wall time (4 API scrapers sequential) — must fit well under 15-min cycle; record for Phase 6 tuning.

## Todo List
- [ ] DevTools verify Vietstock endpoints (or RSS fallback decision) + fixtures
- [ ] core/tickers.py + stoplist + tests
- [ ] VietstockScraper + yaml + skill doc + tests
- [ ] TnckScraper + yaml + skill doc + tests
- [ ] FireAntScraper + yaml + skill doc + tests (401 self-disable)
- [ ] secrets.yaml.example fireant_token
- [ ] Live smoke all 3 + quality ≥95% each
- [ ] Cycle wall-time measurement recorded

## Success Criteria
- 4 API domains (cafef, vietstock, tnck, fireant) live; each ≥95% title+body+date quality on sample.
- FireAnt 401 does not crash pipeline; ERROR logged once/cycle.
- Vietstock articles carry ticker tags where applicable; TNCK uses `related_tickers`.
- All added via config+module only; combined cycle time < 10 min sequential.

## Risk Assessment
- **Vietstock POST protection (CSRF/cookies):** highest-risk item — front-load verification (step 1) with RSS fallback pre-approved.
- **FireAnt token churn:** manual refresh Phase 1; monitoring (Phase 4) alerts on auth failure so operator knows same day.
- **TNCK phrase-per-ticker request volume:** 20 tickers × 3s = 60s+/cycle just TNCK → acceptable; if watchlist grows, rotate subset per cycle (note in skill doc).
- **HTML-partial endpoints on Vietstock:** restrict to JSON endpoints; HTML partials only as documented fallback.

## Security Considerations
- Bearer token only in `config/secrets.yaml` (gitignored); never in logs, YAML domain configs, or fixtures (scrub fixtures before commit).
- POST bodies logged at DEBUG only.
- Respect 3s/domain; back off on 429 (tenacity in Phase 4 formalizes).

## Next Steps
Phase 4 quality layer (can start parallel after Phase 1). Phase 5 RSS adds remaining domains for ≥5 target.
