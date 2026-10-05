# Phase 03 — Vietstock Dedicated Scraper + Full-Raw Capture

## Context links
- research/researcher-01-source-structure.md (Vietstock server-rendered, direct `<img src>`, no lazy, pubDate +0700)
- scout/scout-01-codebase.md (Vietstock uses generic RSS; gaps)
- Code: `project/src/scrapers/rss_generic.py`, `project/config/domains/vietstock.yaml`,
  `project/docs/dev/03-adding-a-source.md`, `project/src/scrapers/__init__.py`, phase-01 `RawStore`

## Overview
- **Date:** 2026-08-13 · **Priority:** P0 · **Depends:** phase-01
- **Description:** Build DEDICATED `src/scrapers/vietstock.py` (`@register("vietstock")`) using RSS feeds
  for the list (proven) but a container-accurate `enrich()` that saves FULL raw detail page via RawStore
  and records capture metadata. Switch `vietstock.yaml` `method: rss` → `method: vietstock`.
- **Implementation status:** PLANNED · **Review status:** NOT REVIEWED

## Key Insights
- Vietstock detail server-rendered; `<article>`/`<h1>`..`<p>`, direct `<img src>` (no data-src/srcset),
  author byline, publish `dd-mm-yyyy HH:MM:SS+07:00`, breadcrumb categories, source attribution present.
- Generic RSS path fetches full page but immediately `extract_content()` (cleans) and never persists raw
  artifact or capture metadata → fails AC2/AC6/AC7/AC8.
- **Dedicated preferred over extending RSS**: (a) container-accurate `content_html` (Vietstock `<article>`
  selector) vs generic trafilatura guess; (b) clean insertion of RawStore-first ordering without risking
  all other RSS domains; (c) room for Vietstock-specific selectors/quirks. DRY kept by reusing RSS helper
  functions (`_decode_feed`, `_parse_entry_date`) via import, not copy.

## Requirements
**Functional**
- List: parse the 4 existing RSS feeds (reuse feedparser + `_decode_feed` + `_parse_entry_date`).
- `parse_item`: Article with url/title/published_at(ISO+07:00)/author/categories/symbols,
  `metadata["language"]="vi"`.
- `enrich`: fetch detail via `get_response()`; RawStore.save FULL page FIRST → `metadata["capture"]`;
  THEN set `content_html` = Vietstock article container (selector), `content_text` via `extract_text`
  (downstream, after raw save). Prefer RSS `content:encoded` ONLY for text fallback, never skip raw save
  if a detail URL exists.
- Preserve img/link/table/caption/author/time/category bytes intact in artifact. Image identifying
  info + URL via RawStore `images[]` manifest (D2, phase-01) — read-only, no HTML mutation.
- **Content-based validity check (D1)**: after RawStore save, `_looks_complete(html,
  ARTICLE_SELECTOR)` (body ≥ `min_body_bytes` AND container present/non-empty AND no empty-render/
  error marker). FALSE → `capture_status="partial"` + `missing:["incomplete_render"]` (phase-05
  candidate). Vietstock ~90% static; only Infographic/E-Magazine may need JS — do NOT flag statically.
- **Text-density fallback for content_html (D5)**: container selector empty/missing → derive
  `content_html` via `readability-lxml`/`goose3`. Parser field ONLY; raw `.html` (saved first) untouched.
- Failure → RawStore failed-branch + `self.errors`, summary fallback, no raise.
**Non-functional**
- No raise; cap `max_details_per_cycle`; rate limit via `http`; robots via phase-04 gate.

## Architecture
New `src/scrapers/vietstock.py`:
```
from src.scrapers.rss_generic import _decode_feed, _parse_entry_date, _clean_title, _inline_content
@register("vietstock")
class VietstockScraper(BaseScraper):
    ARTICLE_SELECTOR = config detail.content_selector default "div.article-content, article"
    fetch_list(): iterate config.rss.feeds → get_bytes → _decode_feed → feedparser (feed isolation)
    parse_item(raw): Article(...) with categories=[feed_name], language vi, tickers tagged
    enrich(article):
        if cap exceeded → summary + detail_deferred; return
        resp = http.get_response(url, referer="https://vietstock.vn/")
        article.metadata["capture"] = raw_store.save("vietstock.vn", url, hash, resp, fetched_at=...)
        if resp is None or not resp.ok: content_text=summary; errors.append(...); return
        self._details_fetched += 1
        html = resp.text
        node = BeautifulSoup(html,"lxml").select_one(self.ARTICLE_SELECTOR)
        if node and node.get_text(strip=True):
            article.content_html = str(node)                       # sub-region ref (primary)
        else:                                                       # D5 density fallback (parser only)
            article.content_html = self._density_extract(html) or html
            article.metadata["capture"].setdefault("missing", []).append("article_container")
        if not self._looks_complete(html, self.ARTICLE_SELECTOR):   # D1 validity check
            article.metadata["capture"]["capture_status"] = "partial"
            article.metadata["capture"].setdefault("missing", []).append("incomplete_render")
        article.content_text = extract_text(article.content_html) or article.summary
```
`_looks_complete`/`_density_extract` = same helpers as CafeF (D1/D5); factor into a shared mixin/util
if both scrapers use them (DRY) — raw `.html` artifact never mutated by either.
Register: add `vietstock` to import line in `src/scrapers/__init__.py`.
Config: `vietstock.yaml` → `method: vietstock`; add `detail.content_selector`; keep feeds.

## Related code files
- **Create:** `project/src/scrapers/vietstock.py`.
- **Modify:** `project/src/scrapers/__init__.py` — add `vietstock` to bottom import.
- **Modify:** `project/config/domains/vietstock.yaml` — `method: vietstock`, `detail.content_selector`.
- **Depends:** `project/src/crawler/raw_store.py` (phase-01); reuse helpers from `rss_generic.py`.

## Implementation Steps
1. Create module; import shared RSS helpers (no copy-paste — DRY).
2. `__init__`: read feeds, cap, watchlist, language, `RawStore`; keep `_details_fetched`.
3. `fetch_list`: mirror RSS feed-isolation loop (WARN + continue on dead feed).
4. `parse_item`: build Article (ISO+07:00 date via `_parse_entry_date`, tag tickers, categories=feed).
5. `enrich`: RawStore-first ordering as above; container selector for `content_html`, empty/miss →
   `_density_extract` (D5); `_looks_complete` validity check (D1) → partial/incomplete_render;
   `extract_text` after. Raw artifact never mutated.
6. Register in `__init__.py`; flip yaml `method`; add `detail.min_body_bytes` (default ~2048).
7. Verify `--once vietstock` returns articles with `metadata["capture"].capture_status=="ok"`.

## Todo list
- [ ] vietstock.py module (dedicated)
- [ ] reuse `_decode_feed`/`_parse_entry_date`/`_clean_title` (DRY)
- [ ] feed-isolation fetch_list
- [ ] parse_item ISO+07:00 + tickers + language vi
- [ ] enrich RawStore-first + container selector + `_density_extract` fallback (D5) + extract_text after
- [ ] `_looks_complete` validity check (D1) → partial/incomplete_render
- [ ] register in __init__.py; yaml method + selector + min_body_bytes
- [ ] --once smoke run

## Success Criteria
- `--once vietstock` writes raw artifacts under `data/raw_html/vietstock.vn/<yyyymmdd>/` byte-equal to
  response; `metadata["capture"].capture_status=="ok"` → **AC1,AC2,AC4,AC5,AC6**.
- `content_html` = article container; full page preserved in artifact → **AC3**.
- No cleaning before raw save (test-asserted) → **AC7**. Fetch failure → failed meta + no raise → **AC8**.
- Dates ISO+07:00; symbols tagged; `language==vi` → convention parity with `03-adding-a-source.md`.

## Risk Assessment
- **Selector drift** (Vietstock markup change): container-miss → D5 text-density fallback for
  `content_html` + `missing[]` flag → raw always captured byte-exact; no crash. Because raw is saved
  first, a broken parser is fixable + re-runnable OFFLINE over stored artifacts (no site re-hit).
- **Switching method breaks generic-RSS assumptions**: vietstock removed from `_rss` set; other RSS
  domains untouched. Confirm orchestrator resolves `method: vietstock` via REGISTRY (it does — key match).
- **Duplicate ticker/date logic** risk → mitigated by importing helpers, not reimplementing.

## Security Considerations
- Header subset (no Set-Cookie) via RawStore. Referer `vietstock.vn/`. robots `/*.js,/*.css,/manager`
  disallow respected (we only fetch article pages) — enforced in phase-04.

## Next steps
- phase-04 adds robots gate both scrapers use. phase-06 adds vietstock tests + fixtures.
