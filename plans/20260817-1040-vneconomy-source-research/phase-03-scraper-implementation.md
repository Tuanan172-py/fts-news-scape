# Phase 03 — Dedicated Scraper Implementation

## Context Links
- Parity target: `src/scrapers/vietstock.py` (copy structure verbatim, swap constants)
- `src/scrapers/capture_mixin.py`, `src/scrapers/rss_generic.py`
- `scout/scout-01-code-contracts.md`
- Depends: phase-01 (selector default), phase-02 (config)

## Overview
- **Date:** 2026-08-17 | **Priority:** High | **Impl status:** Not started | **Review status:** Not reviewed
- **Description:** Create `src/scrapers/vneconomy.py` — `@register("vneconomy")`, `class VnEconomyScraper(CaptureMixin, BaseScraper)`, ~55 lines mirroring vietstock. Register import in `__init__.py`.

## Key Insights
- vietstock is the exact template. Differences from vietstock: `BASE_URL`, domain string `"vneconomy.vn"`, default `content_selector`, docstring.
- DRY: reuse `_clean_title, _decode_feed, _parse_entry_date` from `rss_generic`. Do NOT copy date/title logic.
- `Article` fields used: `symbols=` (not `ticker`), `categories=`, `metadata`. `__init__(self, config, http, dedup)`.
- `_parse_entry_date(raw)` takes the raw entry dict (has published_parsed/published) → returns VN ISO `+07:00`. Handles RFC-2822 GMT automatically (feedparser UTC-normalizes).
- CaptureMixin does bronze save + content_html + failure→summary + robots/crawl-delay/backoff. Scraper only sets `content_text` on success.

## Requirements
**Functional**
- `fetch_list()`: loop 3 feeds → `http.get_bytes` → `feedparser.parse(_decode_feed(raw))`; feed-level isolation (append error, continue); emit per-entry dict.
- `parse_item(raw)`: `_clean_title`; drop if no url/title; summary via `extract_text` if HTML else raw; `_parse_entry_date(raw)`; `tag_tickers(title+summary, watchlist)`; `source_domain = urlparse(url).netloc.removeprefix("www.")`.
- `enrich(article)`: cap check (`max_details`) → over cap set `content_text=summary`, `metadata["detail_deferred"]=True`; else `_capture_and_extract(article, "vneconomy.vn", f"{BASE_URL}/", self.content_selector)`; on None return; else increment + `content_text = extract_text(content_html) or summary`.
- `@register("vneconomy")`.

**Non-functional**
- ≤ ~60 lines. Vietnamese docstring matching repo style. No new deps.

## Architecture
```
fetch_list (RSS×3) → parse_item (Article) → BaseScraper.run dedup → enrich
   enrich → CaptureMixin._capture_and_extract → RawStore.save (BRONZE byte-exact)
          → content_html = select_one(content_selector) | _density_extract fallback
SilverBuilder (offline, unchanged) reads bronze → silver JSON
```

## Related Code Files
- CREATE `src/scrapers/vneconomy.py`
- MODIFY `src/scrapers/__init__.py` — add `vneconomy` to bottom import tuple (alpha order): `cafef, fireant, rss_generic, tnck, vietstock, vndirect, vneconomy`

## Implementation Steps
1. Copy `vietstock.py` → `vneconomy.py`.
2. Set `BASE_URL = "https://vneconomy.vn"`.
3. Rename class → `VnEconomyScraper`; decorator `@register("vneconomy")`.
4. `__init__`: default `content_selector` = phase-01 value (e.g. `"div.detail__content, article"`); keep watchlist/language/max_details/`_init_capture()`.
5. `enrich`: change domain arg to `"vneconomy.vn"`, referer `f"{BASE_URL}/"`.
6. `parse_item`: identical to vietstock (author stored as-is from RSS).
7. (Optional, YAGNI-guarded) Author "K " prefix cleanup: ONLY if phase-01 confirms noise present AND a downstream consumer of `article.author` exists. Silver derives author independently → default = do nothing. If added: `author = re.sub(r"^K\s+", "", raw["author"]).strip()`. Document choice.
8. Update docstring (VnEconomy specifics: no content:encoded, premedia CDN, direct src, 1s crawl-delay).
9. Add import in `__init__.py`.
10. Smoke: `python -c "from src.scrapers import REGISTRY; print('vneconomy' in REGISTRY)"` → True.

## Todo List
- [ ] Create vneconomy.py from vietstock template
- [ ] BASE_URL + class name + @register
- [ ] content_selector default = phase-01
- [ ] enrich domain "vneconomy.vn"
- [ ] reuse rss_generic helpers (DRY)
- [ ] add import to __init__.py
- [ ] REGISTRY smoke check True
- [ ] decide author-prefix cleanup (default: skip, YAGNI)

## Success Criteria
- `"vneconomy" in REGISTRY and REGISTRY["vneconomy"] is VnEconomyScraper`.
- File imports cleanly; no new dependency.
- Structure diff vs vietstock.py limited to constants/selector/docstring.

## Risk Assessment
- **R1:** Using `ticker=` instead of `symbols=` → follow vietstock exactly (`symbols=`).
- **R2:** Over-engineering author/date parsing → silver derives from raw; keep scraper thin (KISS/YAGNI).
- **R3:** Wrong `_parse_entry_date` arg → pass the raw entry dict, not whole item (matches vietstock `_parse_entry_date(raw)`).
- **R4:** Selector miss → density fallback covers; bronze unaffected.

## Security Considerations
- All network via CaptureMixin: robots gate + crawl-delay + backoff enforced. No direct `http.get` bypass in enrich (unlike generic RSSScraper). No secrets.

## Next Steps
- Feeds phase-04 (tests import `VnEconomyScraper`) + phase-05 (e2e run).
