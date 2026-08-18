# Scout — Exact Code Contracts (direct reads)

Files read verbatim by main agent. Complements researcher-02 (integration map).

## Reference scraper: vietstock (the parity target)
`src/scrapers/vietstock.py` — `@register("vietstock")`, `class VietstockScraper(CaptureMixin, BaseScraper)`.
- `__init__`: reads `rss.feeds`, `detail.content_selector`, `detail.max_details_per_cycle`, `watchlist`, `language`; calls `self._init_capture()`.
- `fetch_list()`: loop feeds → `self.http.get_bytes(url)` → `feedparser.parse(_decode_feed(raw))`; feed-level isolation (append to `self.errors`, continue). Emits dict per entry (link/title/summary/author/published_parsed/_feed_name).
- `parse_item(raw)`: `_clean_title`, `extract_text` for summary, `_parse_entry_date`, `tag_tickers(title+summary, watchlist)`, `source_domain = urlparse(url).netloc.removeprefix("www.")`. Returns `Article`.
- `enrich(article)`: cap check → `article.content_text=summary; metadata["detail_deferred"]=True` when over cap; else `html=self._capture_and_extract(article,"vietstock.vn",f"{BASE_URL}/",self.content_selector)`; on None return; else `content_text=extract_text(content_html) or summary`.
- DRY: imports `_clean_title,_decode_feed,_parse_entry_date` from `rss_generic`.

## CaptureMixin (bronze persistence) — `src/scrapers/capture_mixin.py`
- `_init_capture()`: builds `RawStore(capture.raw_dir | "data/raw_html")`, `min_body_bytes` (dflt 2048), `RobotsGate` (if `compliance.respect_robots`), `SourceBackoff`.
- `_capture_and_extract(article, domain, referer, selector)`: robots gate → crawl-delay → backoff → `http.get_response` → **RawStore.save FIRST (byte-exact, never mutated)** → set `content_html` = `soup.select_one(selector)` (or `_density_extract` fallback) → D1 validity (`_looks_complete`) marks `capture_status=partial`. Returns html or None (never raises).
- Subclass MUST provide `self.http/config/name/errors`.

## cafef parallel (API variant) — `src/scrapers/cafef.py`
Same `CaptureMixin` pattern, `content_selector` default `div#mainContent`. Confirms mixin is source-agnostic (works for RSS-list + detail-fetch).

## Registry/dispatch — `src/scrapers/__init__.py`
- `REGISTRY: dict[str,type[BaseScraper]]`, `@register(name)` decorator.
- Bottom-of-file imports trigger registration: currently `cafef, fireant, rss_generic, tnck, vietstock, vndirect`. **Must add `vneconomy`.**
- Dispatch (per researcher-02, orchestrator): `REGISTRY.get(cfg["name"]) or REGISTRY.get(f"_{cfg['method']}")` → name-specific beats generic `_rss`.

## Silver layer is DOMAIN-AGNOSTIC — `src/pipeline/silver_builder.py`
- `SilverBuilder.build(meta, raw_bytes)` PURE/OFFLINE/DETERMINISTIC. Reads `meta.json` + bronze bytes → silver dict. Domain derived from raw_html path partition (`_domain_of`).
- Cleaned-text fallback chain: trafilatura(high) → extract_text/BS4(medium) → join paragraphs(low) → empty.
- `built_at = meta.fetch_ts` (re-derivable). `write_silver` mirrors bronze partition `data/silver/<domain>/<YYYYMMDD>/<article_id>.json`.
- **⇒ No silver_builder change needed for a new domain.** Bronze capture quality (good selector) is what determines silver quality.

## Silver schema — `schemas/silver-v1.schema.json`
Required: `silver_schema_version, article_id, source_url, domain, content_sha256, cleaned_text(minLength1), built_from_raw_path`. Optional: structure{headings/paragraphs/tables/links}, images, language, extraction_quality(high|medium|low|empty).

## Existing config — `config/domains/vneconomy.yaml`
`method: rss`, `enabled: false`, 3 feeds (chung-khoan/tai-chinh/thi-truong), `detail.extract_full:true`, `max_details_per_cycle:30`. Pitfall recorded: content:encoded declared but absent → detail-fetch. **Missing vs vietstock: `capture:` + `compliance:` blocks, `content_selector`, `language`.**

## Net delta to reach parity
Create `src/scrapers/vneconomy.py` (CaptureMixin, ~50 lines, mirror vietstock); add import in `__init__.py`; rewrite `vneconomy.yaml` (method→vneconomy, enabled→true, add capture/compliance/content_selector/language); add `tests/test_vneconomy.py` + fixtures. Zero pipeline/orchestrator/silver changes.
