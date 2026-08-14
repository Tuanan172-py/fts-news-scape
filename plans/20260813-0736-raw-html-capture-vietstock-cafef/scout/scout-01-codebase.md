# Scout — Codebase Map (raw-HTML capture, Vietstock + CafeF)

Scope: existing Python scraper pipeline under `project/`. Files read directly (not inferred).

## Architecture (existing)
Template-method pipeline. `BaseScraper.run()` orchestrates: `fetch_list()` → `parse_item()` → dedup → `enrich()` → mark seen. Scrapers never write DB; `orchestrator` enqueues `ScrapeResult.new` to `DBWriter`.

- `project/src/core/base_scraper.py` — `BaseScraper` (ABC). Hooks: `fetch_list()`, `parse_item()`, optional `enrich(article)`. `enrich()` is the designated place to "fetch trang chi tiết, điền content_html/content_text". Never raises — errors → `self.errors`.
- `project/src/core/models.py` — `Article` dataclass. Has `content_html` (raw-ish HTML), `content_text` (cleaned), `metadata: dict`, `fetched_at`. `to_row()`/`from_row()` map to `articles` table. **No field for raw-artifact path, HTTP status, capture status, or fetch headers.**
- `project/src/crawler/http_client.py` — single `HTTPClient` (requests.Session). Methods: `get()` (→text), `get_bytes()` (→bytes), `get_json()`, `post_json()`, `get_response()` (→full `requests.Response`, exposes status/headers). Rate limit per-domain (default 3.0s), UA rotation, retry 429/5xx, truststore for VN certs. **No JS rendering. No raw-response persistence.**
- `project/src/db/store.py` — SQLite `ArticleStore`, schema v2, WAL. `articles` table columns incl. `content_html`, `content_text`, `metadata_json`. `INSERT OR IGNORE` on `url`/`url_title_hash`. **No raw-HTML/capture table.**
- `project/src/db/writer.py`, `dedup.py` — single-writer + dedup (SHA-256 url+title, fuzzy title).
- `project/src/processor/extractor.py` — trafilatura. `extract_content(url, html)` → `{raw_html, content, status}` (raw_html = full page passed in). `extract_text(fragment)` → cleaned text. **This is downstream cleaning — must NOT run in the raw-capture phase per task.**
- `project/src/orchestrator.py` — scheduler (`--once <name>`), APScheduler threaded (worker thread ≠ dedup thread; `check_same_thread=False`).
- `project/src/scrapers/__init__.py` — `register(name)` decorator + registry. New modules imported at bottom of file.

## Target sources — current state
### CafeF — `project/src/scrapers/cafef.py` (+ `config/domains/cafef.yaml`)
- Dedicated module `@register("cafef")`. List via JSON API `.../PageNew/News.ashx` (`Type=1` mandatory, symbol per watchlist). `enrich()` fetches detail via `http.get()`, keeps only `BeautifulSoup(...).select_one("div#mainContent")` into `content_html`, then `extract_text` → `content_text`. Cap `max_details_per_cycle=30`.
- **Gaps vs task**: (a) stores only `#mainContent` node, not full raw HTML page; (b) no raw response saved to disk; (c) runs trafilatura cleaning inline; (d) no HTTP status/headers/capture-status recorded; (e) discards page-level `<head>` meta (og:, article:published_time).

### Vietstock — `config/domains/vietstock.yaml` only (NO dedicated module)
- Uses generic `RSSScraper` (`@register("_rss")`, `project/src/scrapers/rss_generic.py`). `method: rss`. Feeds: tin-moi / chung-khoan / doanh-nghiep / vi-mo. `enrich()` → if `content:encoded`≥500 use inline, else `http.get()` full page → `extract_content()` (raw_html=full page, but immediately cleaned to content_text). Cap 30.
- Config note: internal API needs browser session (unused); RSS description contains `<img>`; pubDate +0700.
- **Gaps vs task**: same as CafeF — full raw page HTML is fetched but not persisted as an inspectable artifact; cleaning runs inline; no capture metadata; RSS-only means no dedicated container/selector research applied.

## Key reuse points for the plan
- `enrich()` hook is the correct insertion point for raw capture on both scrapers.
- `HTTPClient.get_response()` already returns status + headers → use it (not `get()`) to record capture metadata.
- `Article.metadata` (JSON) + a new raw-artifact store (disk) avoid schema churn; or add columns/table to `store.py`.
- Rate limiting / retry / UA already centralized — reuse, do not bypass.
- `docs/dev/03-adding-a-source.md` defines conventions: no-raise, ISO+07:00 dates, cap details, `metadata["language"]`, tests with `FakeHTTP`.

## Confirmed rendering (live check)
- **CafeF detail page = server-rendered** (plain GET returns full body, author `Khánh Hân`, datetime, category `Doanh nghiệp`, captioned image). No JS needed. Container historically `div#mainContent`.
- **Vietstock detail = server-rendered** (researcher-01). Direct `<img src>`, no lazy-load.
- ⇒ Existing `requests` client suffices for base capture; headless browser only as optional fallback.

## Related files (edit/create targets)
- Edit: `src/scrapers/cafef.py`, `config/domains/cafef.yaml`, `config/domains/vietstock.yaml`, `src/core/models.py`, `src/db/store.py`, `src/scrapers/__init__.py`.
- Create: `src/scrapers/vietstock.py` (dedicated), `src/crawler/raw_store.py` (raw artifact writer), tests under `tests/`.

## Unresolved questions
1. Persist raw HTML on filesystem (`data/raw_html/...`) vs BLOB in SQLite vs both? (disk recommended — independently inspectable per acceptance criteria.)
2. Keep Vietstock on generic RSS + capture layer, or build dedicated `vietstock.py`? (dedicated gives container-accurate capture + secondary-API handling.)
3. Should raw capture run for ALL new articles (uncapped) or keep 30/cycle cap? Task wants full capture → cap may need raising or a backfill queue.
