# VnEconomy Integration Mapping: Bronze → Silver Scraper

## Registry & Dispatch (src/scrapers/__init__.py:15-19)

**How it works:**
- `@register("name")` decorator maps scraper class name → REGISTRY dict
- `build_scraper()` (orchestrator.py:52) uses lookup: `REGISTRY.get(cfg["name"]) or REGISTRY.get(f"_{cfg['method']}")`
- **Priority:** domain-name specific class > generic `_method` class (e.g., vietstock > _rss)

**VnEconomy config (vneconomy.yaml) currently:**
```yaml
method: rss           # generic RSS scraper if _rss method
enabled: false        # disabled 2026-08-03
```

**To use dedicated scraper:** change `method: vneconomy` (not "rss"), then register with `@register("vneconomy")`.

**Impact on pipeline:** None. Orchestrator.run_cycle() → build_scraper() → instantiate class → run().

---

## Scraper Architecture (src/core/base_scraper.py)

**BaseScraper template:**
1. `fetch_list()` → list[dict] (raw RSS entries / API JSON / HTML)
2. `parse_item(raw)` → Article | None (transform raw → Article)
3. `enrich(article)` → None (optional: fetch detail page, store raw HTML)

**Silver field requirements (src/core/models.py):**
Article model fields:
- url, title, summary, author, published_at, source_domain, language, ticker (optional)
- content_html, content_text (set by enrich)
- processed_at (set by run())

**Dedup flow:** BaseScraper.run() (line 58-67):
- Check if (url, title) seen → skip
- Check fuzzy title similarity → skip + mark seen (graceful dedup)
- Save new articles to dedup cache after enrich

**Error handling:** All exceptions caught in try/except blocks, accumulated in self.errors, **never raised**. ScrapeResult.errors returned for logging.

---

## Pipeline: Bronze → Silver (no orchestrator changes needed)

**Silver builder (src/pipeline/silver_builder.py:1-80):**
- Input: meta.json dict + raw bytes from RawStore
- **Deterministic:** same raw → same silver (built_at from meta.fetch_ts, not now)
- Process: parse lang, extract content (trafilatura), structure (BeautifulSoup)
- Output: Silver JSON record (schema/silver-v1.schema.json)

**Orchestrator run_cycle (src/orchestrator.py:84-150):**
1. Load domain config → build_scraper() → run()
2. Enqueue new articles to DBWriter (single-writer thread)
3. DBWriter.enqueue() → SQLite insert (dedup + write Bronze raw_html path)
4. **Derive pipeline (separate):** re-derive Silver from Bronze on-demand (incremental)

**Conclusion:** Adding domain **requires 0 pipeline code changes**. Config + scraper + registration = complete.

---

## Config Loading & Domain Discovery

**List domains (src/core/config.py):**
- Scans config/domains/*.yaml
- Filters by `enabled: true` (or missing, default true)
- Returns list of domain names

**Load domain config:**
- Read config/domains/<name>.yaml → dict
- Validate keys (name, method, rate_limit, timeout)
- Optional: rss.feeds, detail.*, capture.*, compliance.*

**VnEconomy config structure (existing vneconomy.yaml):**
```yaml
name: vneconomy              # Must match filename
method: vneconomy            # Change from "rss" to "vneconomy" for dedicated
enabled: true                # Change from false to true
rate_limit: 3.0
timeout: 30
language: vi                 # (optional, inferred from content)
rss:
  feeds:
    - url, name              # List of RSS URLs
detail:
  extract_full: true
  max_details_per_cycle: 30  # (optional, for enrich)
capture:
  raw_dir: "data/raw_html"   # (optional, if using CaptureMixin)
compliance:
  respect_robots: true       # (optional)
```

**Toggle:** Set `enabled: true` in vneconomy.yaml. No other config files to change.

---

## Testing: Fixture Pattern (tests/conftest.py + test_cafef.py)

**Test structure for CafeFScraper:**
- `tests/fixtures/cafef_list_response.json` — captured real API response
- `tests/fixtures/cafef_detail_page.html` — captured real HTML
- `_fakes.py::FakeHTTP` — mock http_client with canned responses
- `test_cafef.py`: instantiate scraper with FakeHTTP → run() → assert results

**VnEconomy test must mirror:**
1. Create `tests/fixtures/vneconomy_list.rss` (captured real RSS feed)
2. Create `tests/fixtures/vneconomy_detail_page.html` (captured detail page if enrich used)
3. Write `tests/test_vneconomy.py` with FakeHTTP mock
4. Test parse_item(), enrich() (if any), full run()

**Key fixture pattern (test_cafef.py:70-80):**
```python
def test_happy_path_real_fixture(env, fixture_list, fixture_detail):
    http = FakeHTTP(list_json=fixture_list, detail_html=fixture_detail)
    scraper = CafeFScraper(_config(), http, env)
    result = scraper.run()
    assert result.fetched == len(fixture_list["Data"])
```

---

## Files to Create/Modify

### Create (3 files):

1. **src/scrapers/vneconomy.py**
   - Class `VnEconomyScraper(BaseScraper)` with `@register("vneconomy")`
   - Methods: fetch_list() (parse RSS feeds), parse_item(), enrich() (optional)
   - ~100–150 lines (similar length to vietstock.py)

2. **tests/test_vneconomy.py**
   - Setup FakeHTTP with vneconomy_list.rss + optional detail.html
   - Test happy path, edge cases (malformed date, missing title, etc.)
   - ~80 lines

3. **tests/fixtures/vneconomy_list.rss**
   - Captured real RSS from https://vneconomy.vn/chung-khoan.rss (2–3 entries)
   - ~200 lines

### Modify (2 files):

1. **src/scrapers/__init__.py** (line 24–31)
   - Add import: `from src.scrapers import vneconomy`
   - Triggers @register("vneconomy") at module load

2. **config/domains/vneconomy.yaml** (line 3, 2)
   - Change `method: rss` → `method: vneconomy`
   - Change `enabled: false` → `enabled: true`

### Optional files (for raw HTML capture):

- **tests/fixtures/vneconomy_detail_page.html** — if enrich() fetches details

---

## Shared Helpers (reuse from rss_generic.py)

**If VnEconomy uses RSS generic parsing:**
- `rss_generic._parse_rss_feed()` — fetch + parse feedparser
- `rss_generic._parse_entry_date()` — standardize pubDate to ISO
- `rss_generic._clean_title()` — strip HTML entities
- Subclass generic `RSSScraper` or copy-paste + customize selectors

**If VnEconomy needs detail fetch (like vietstock):**
- Use CaptureMixin from src/scrapers/capture_mixin.py
- Call `self._capture_and_extract(article, domain, referer, selector)` in enrich()
- Stores raw HTML in RawStore, sets content_html from extraction

---

## Unresolved Questions

1. **Detail page fetch:** Does VnEconomy RSS `<content:encoded>` have full article, or require detail fetch like Vietstock?
   - **Current config:** pitfalls note "content:encoded khai báo nhưng item KHÔNG chứa" → likely needs detail fetch
   - **Action:** Implement enrich() with detail capture (use CaptureMixin pattern)

2. **Date format:** What timezone in VnEconomy RSS pubDate? (Vietstock: +0700)
   - **Action:** Test captured feed, adjust `_parse_entry_date()` if needed

3. **Ticker extraction:** VnEconomy articles mention stock symbols? Extract via regex or keyword lookup?
   - **Action:** Check fixtures, use src/core/tickers.py fuzzy matching if present
