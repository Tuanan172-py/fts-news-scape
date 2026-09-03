# Phase 05 — RSS Layer: Generic Collector + Trafilatura Full-Article Extraction

> **UPDATE 2026-07-24 (verified — see `reports/01-verification-report.md`):** Vietstock RSS is now the PRIMARY method for Vietstock (internal API unreachable — Phase 3 scope change). Verified live: `https://vietstock.vn/rss` index → 60 feeds, RSS 2.0, pubDate `+0700`. Start feeds: `/0/tin-moi.rss`, `/144/chung-khoan.rss`, `/733/doanh-nghiep.rss`, `/761/kinh-te/vi-mo.rss`. VnEconomy verified: `https://vneconomy.vn/tin-moi.rss`, `chung-khoan.rss`, `tai-chinh.rss` — RSS 2.0 with `content:encoded` (full content in feed → less enrich needed). Domain configs: vietstock.yaml is `method: rss` (not `vietstock_rss` fallback naming).

## Context Links
- Parent plan: [plan.md](plan.md)
- Depends on: [phase-01-foundation-refactor.md](phase-01-foundation-refactor.md), [phase-04-quality-layer.md](phase-04-quality-layer.md) (retry/monitor/notify plumbing)
- Spec: `docs/system-prompt.md` §8 (RSS = priority 1 method), §13 Sprint 4
- Research: [research/researcher-02-ops-sentiment-report.md](research/researcher-02-ops-sentiment-report.md) §5 (verified 2026 feed URLs), `docs/rss-reference.md` (existing feed notes)
- Existing code: `src/rss/collector.py` (feedparser fetch, 87 LOC, working)

## Overview
- **Date:** 2026-07-24
- **Description:** Fold existing RSS collector into `RSSScraper(BaseScraper)` — one generic class, N feed configs. Sources: VnExpress Kinh doanh, Báo Đầu tư, VnEconomy (replacing dormant NDH), ĐTCK/TNCK RSS (if exists — else covered by Phase 3 API), Vietstock RSS (as fallback for Phase 3 API scraper). Full-article extraction: fetch entry URL → store raw page HTML + trafilatura clean text.
- **Priority:** Medium-High (completes ≥5 domains + broad macro/policy coverage that symbol APIs miss)
- **Implementation status:** Not started
- **Review status:** Not reviewed

## Key Insights
- RSS is spec priority #1 method — cheapest coverage for Layer 0-1 sources; API scrapers (Phases 2-3) cover symbol-specific depth, RSS covers vĩ mô/chính sách/quốc tế breadth.
- Researcher-02 verified (2026): VnExpress `https://vnexpress.net/rss/kinh-doanh.rss` (already in collections.yaml), Báo Đầu tư `https://baodautu.vn/rssMain.html` (index page — actual per-category feed URLs must be extracted from it), VnEconomy `https://vneconomy.vn/rss.html` (index — same), Vietstock `https://vietstock.vn/rss` active. NDH dormant → drop/disable (plan.md Q5).
- One `RSSScraper` class instantiated per domain config (not per feed) — each domain yaml lists its feeds; keeps per-domain heartbeat/rate-limit semantics.
- RSS summary alone fails spec quality bar (body needed) → `enrich()` fetches article page: raw HTML preserved (spec hard rule) + `trafilatura.extract()` clean text; per-domain optional CSS selector override (`config/domains/*.yaml html.selectors.body`) when trafilatura precision drops (existing `domains.yaml` selectors for vnexpress reusable here — migrate then delete old file).
- Existing `src/processor/extractor.py` (trafilatura + readability fallback) already works — reuse inside enrich, don't rewrite.
- RSS `pubDate` parsing: feedparser gives `published_parsed` struct_time (UTC-normalized) → convert to `Asia/Ho_Chi_Minh` ISO; fallback `dateutil` on raw string.

## Requirements
1. `RSSScraper(BaseScraper)` generic — new RSS domain = yaml only, zero code.
2. 4 RSS domain configs: vnexpress, baodautu, vneconomy, vietstock_rss (vietstock_rss doubles as Phase 4 fallback target for vietstock API scraper).
3. Full-article extraction with raw HTML + clean text; detail cap per cycle (default 30/domain).
4. Ticker tagging via `core/tickers.py` (Phase 3) on title+summary.
5. Feed-level failure isolation: one dead feed → WARN + continue others in domain.
6. VnExpress selector refinement only if trafilatura quality <95% on sample (spec Sprint 4 conditional item).
7. Tests: happy (fixture XML) + edge (malformed XML, entry without link, future-dated pubDate).

## Architecture
```
src/scrapers/rss_generic.py    # RSSScraper(BaseScraper)
config/domains/vnexpress.yaml, baodautu.yaml, vneconomy.yaml, vietstock_rss.yaml
docs/skills/rss-sources.md     # one skill doc covering all RSS domains + feed inventory
tests/test_rss_scraper.py + tests/fixtures/vnexpress_feed.xml
```
**vnexpress.yaml sketch:**
```yaml
name: vnexpress
enabled: true
method: rss
rate_limit: 3.0
rss:
  feeds:
    - {url: "https://vnexpress.net/rss/kinh-doanh.rss", name: "VnExpress Kinh Doanh"}
    - {url: "https://vnexpress.net/rss/chung-khoan.rss", name: "VnExpress Chứng khoán"}  # verify exists
detail:
  extract_full: true
  max_details_per_cycle: 30
html:
  selectors: {body: "article.fck_detail"}   # optional override, migrated from old domains.yaml
pitfalls: "pubDate RFC822; summary contains img tag + description mix"
```
**Flow:** `fetch_list()` → feedparser per feed (via HTTPClient.get for rate-limit/UA control, `feedparser.parse(text)`) → entries. `parse_item()` → Article(url, title, summary=entry.summary stripped, published_at from published_parsed→VN tz). `enrich()` → existing `extractor.extract_content(url)` extended to return `(raw_html, clean_text)`; selector override path if configured.

## Related Code Files
**Create:** `src/scrapers/rss_generic.py`, `config/domains/vnexpress.yaml`, `config/domains/baodautu.yaml`, `config/domains/vneconomy.yaml`, `config/domains/vietstock_rss.yaml`, `docs/skills/rss-sources.md`, `tests/test_rss_scraper.py`, `tests/fixtures/vnexpress_feed.xml`
**Modify:** `src/processor/extractor.py` (return raw_html alongside clean text; currently discards raw), `src/rss/collector.py` (reduce to thin feed-fetch util used by RSSScraper — or absorb + delete, prefer absorb), `config/collections.yaml` (deprecate: superseded by per-domain configs — delete after migration), `docs/rss-reference.md` (update verified feed inventory)
**Delete:** `config/domains.yaml` (old skeleton — selectors migrated into per-domain files), `config/collections.yaml` (after migration), `src/rss/collector.py` (after absorption into rss_generic.py; keep `src/rss/` removal clean)

## Implementation Steps
1. Feed verification pass (live): resolve concrete feed URLs — open `https://baodautu.vn/rssMain.html` + `https://vneconomy.vn/rss.html` index pages, pick finance/securities/investment category feeds (2-3 per domain); test-fetch each with feedparser (`bozo` flag check); check `https://vnexpress.net/rss/chung-khoan.rss` existence; check TNCK RSS (if found, add `tnck_rss.yaml` as fallback for Phase 3 API). Record all in `docs/rss-reference.md`.
2. Extend `src/processor/extractor.py::extract_content(url, http)` → returns `{"status", "raw_html", "content", "method"}`; raw_html = full response text (spec: preserve before processing); optional `selector` param → BS4 select for content_html scope.
3. Implement `RSSScraper`: constructor takes domain config; `fetch_list()` loops feeds — fetch via HTTPClient (UA + rate limit), `feedparser.parse`; `bozo` + no entries → WARN + skip feed; tag entries with feed_name.
4. `parse_item()`: url/title/summary; `published_at`: `datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()`; missing → fetched_at + WARN (counts against quality metric — monitor). Strip HTML tags from summary for text; symbols = `tag_tickers(title+summary)`.
5. `enrich()` with cap: call extractor; `content_html` = selector-scoped node if configured else full raw page; `content_text` = trafilatura output; extraction fail → summary as body, `is_full_content` metadata false.
6. Write 4 domain yamls with verified feed URLs from step 1.
7. `docs/skills/rss-sources.md`: feed inventory table (domain, feed URL, category, verified date, quirks).
8. Tests: fixture-driven happy path (5 entries → 5 Articles, VN tz dates); malformed XML → 0 items, error logged, no raise; entry missing link → skipped; dedup on rerun → 0 new.
9. Live run all 4 RSS domains; `scripts/verify_quality.py` per domain; if vnexpress <95% → refine `article.fck_detail` selector (spec conditional); recheck.
10. Migrate + delete `config/collections.yaml` and `config/domains.yaml`; final grep for references.

## Todo List
- [ ] Live feed URL verification (baodautu/vneconomy index resolution, vnexpress chung-khoan, TNCK RSS)
- [ ] extractor.py returns raw_html + selector support
- [ ] RSSScraper class (feed isolation, tz-correct dates)
- [ ] Ticker tagging integration
- [ ] 4 domain yamls
- [ ] docs/skills/rss-sources.md + rss-reference.md update
- [ ] tests/test_rss_scraper.py green
- [ ] Live quality ≥95%/domain; vnexpress selector refinement if needed
- [ ] Delete collections.yaml + domains.yaml after migration

## Success Criteria
- ≥3 new RSS domains live (vnexpress, baodautu, vneconomy) → total system domains ≥6 (>spec ≥5).
- ≥95% RSS articles have title+body+date; raw page HTML stored for every enriched article.
- Dead feed doesn't fail domain; domain failure doesn't fail cycle.
- Adding hypothetical new RSS source = 1 yaml file, no code (dry-run test with vietstock_rss.yaml proves).

## Risk Assessment
- **Feed URL rot** (NDH precedent): verification step first; monitor catches silent feed death (0 articles heartbeat trend).
- **Trafilatura precision on VN layouts:** readability fallback already in extractor; per-domain selector override as final lever.
- **Duplicate coverage RSS vs API** (vietstock_rss vs vietstock API): expected — layer-1 hash dedup + Phase 4 fuzzy layer handle; cross-check in Phase 6 e2e.
- **VnExpress summary-only entries with paywall/interactive pages:** mark `is_full_content=false`, keep summary — counts against quality; monitor per-feed rate.

## Security Considerations
- Feeds are public, no auth. XML parsing via feedparser (tolerant, no XXE by default) — never pass feed XML to lxml with entity resolution enabled.
- Stored raw HTML from arbitrary pages: same escaping caveat as Phase 2 (no unescaped rendering later).

## Next Steps
Phase 6 — orchestrator integrates all 7-8 scrapers, 24h stability run, tuning, final docs.
