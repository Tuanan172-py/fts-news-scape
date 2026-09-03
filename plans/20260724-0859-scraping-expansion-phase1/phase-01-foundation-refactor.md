# Phase 01 — Foundation Refactor

## Context Links
- Parent plan: [plan.md](plan.md)
- Depends on: nothing (first phase, blocks all others)
- Spec: `C:\Users\An Thanh Pham\Documents\web-monocle\docs\system-prompt.md` §11 (architecture), §12 (constraints), §13 Sprint 1
- Scout audit: [scout/scout-01-report.md](scout/scout-01-report.md) — GAP #1 (WAL), #2 (Hermes), #3 (BaseScraper), #6 (logging)
- Research: [research/researcher-01-frameworks-report.md](research/researcher-01-frameworks-report.md) (stack), [research/researcher-02-ops-sentiment-report.md](research/researcher-02-ops-sentiment-report.md) §2 (SQLite WAL + single-writer)
- Existing code: `src/run_collection.py`, `src/db/store.py`, `src/db/dedup.py`, `src/crawler/http_client.py`, `src/processor/pipeline.py`

## Overview
- **Date:** 2026-07-24
- **Description:** Refactor MVP skeleton into extensible base: `BaseScraper` ABC, unified `Article` model, SQLite WAL + single-writer queue, loguru centralized logging, per-domain YAML config schema, de-Hermes cleanup, README rewritten to reality.
- **Priority:** Critical (blocks all phases)
- **Implementation status:** Not started
- **Review status:** Not reviewed

## Key Insights
- Current code is functional-module style (`fetch_collection()`, `process_entry()`); spec demands class hierarchy so new domain = YAML + 1 subclass, no orchestrator edits.
- `store.py` opens new connection per save, no WAL, `INSERT OR REPLACE` (destroys history) — must become UNIQUE-constraint insert + single-writer thread.
- Dedup uses JSON file `data/dedup_cache.json` — migrate into SQLite (same DB, WAL-safe).
- Hermes remnants: README (hermes cron create, skills section), `skills/web-monocle-cron.md`, `skills/web-monocle-rss.md`, `scripts/financial_collector.py`, `scripts/deploy_crons.sh`, telegram targets in `config/collections.yaml`. Also README lists 9 files that don't exist (scheduler.py, api/collector.py, anti_bot.py, summarizer.py, entity_extract.py, telegram.py, models.py, clickhouse.py, generic_scraper/content.py).
- `docs/architecture.md` mentions ClickHouse — contradicts spec; SQLite-only.
- Keep `HTTPClient` core but raise default rate limit 2.0→3.0s and route errors to logger; add requests-cache + tenacity in Phase 4 (retry hardening) — Phase 1 only wires the seams.

## Requirements
1. `BaseScraper` abstract class (template method pattern) — spec §15.
2. Unified `Article` dataclass with `content_html` (raw preserved) + `content_text` fields — spec §9.
3. SQLite: WAL mode, `busy_timeout=5000`, single-writer queue thread — spec §12, research-02 §2.
4. Centralized loguru logging replacing all `print()` — spec §4.3.
5. Config schema: per-domain YAML under `config/domains/`, global `config/settings.yaml`, `config/watchlist.yaml`, `config/secrets.yaml` (gitignored).
6. De-Hermes: no Hermes reference anywhere; standalone entry points.
7. README matches actual tree; no ClickHouse/Telegram/Hermes claims.
8. Graceful shutdown (no DB corruption on kill) — spec §12.

## Architecture
```
src/
├── core/
│   ├── models.py        # Article dataclass (url, title, summary, content_html, content_text,
│   │                    #   published_at, author, source_domain, symbols, categories,
│   │                    #   sentiment, sentiment_score, fetched_at, metadata: dict)
│   ├── base_scraper.py  # BaseScraper ABC — template method run()
│   ├── config.py        # load_settings(), load_domain_config(name), load_watchlist(), load_secrets()
│   └── logging.py       # setup_logging() → loguru, logs/monocle.log rotation 50MB, retention 14d
├── crawler/http_client.py   # keep; default delay 3.0s; logger not print
├── db/
│   ├── store.py         # ArticleStore: schema v2, WAL pragmas, insert_batch via writer
│   ├── writer.py        # DBWriter thread: queue.Queue → batch INSERT in BEGIN IMMEDIATE txn
│   └── dedup.py         # SQLite-backed (table seen_articles), same DB
```
**BaseScraper template method:**
```python
class BaseScraper(ABC):
    name: str                     # e.g. "cafef"
    def __init__(self, config: dict, http: HTTPClient, dedup: DedupCache): ...
    def run(self) -> ScrapeResult:        # final — DO NOT override
        raw_items = self.fetch_list()     # abstract: RSS/API/HTML fetch
        articles = [self.parse_item(i) for i in raw_items]  # abstract
        new = [a for a in articles if a and not self.dedup.is_duplicate(a.url, a.title)]
        for a in new: self.enrich(a)      # hook: default no-op (detail fetch, full text)
        return ScrapeResult(scraper=self.name, fetched=len(raw_items), new=new, errors=self.errors)
    @abstractmethod
    def fetch_list(self) -> list[dict]: ...
    @abstractmethod
    def parse_item(self, raw: dict) -> Article | None: ...
    def enrich(self, article: Article) -> None: ...   # optional override
```
**DB schema v2 (`articles` table):**
```sql
CREATE TABLE IF NOT EXISTS articles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL UNIQUE,
  url_title_hash TEXT NOT NULL UNIQUE,   -- sha256(url+title)
  title TEXT NOT NULL, summary TEXT,
  content_html TEXT, content_text TEXT,
  published_at TEXT, author TEXT,
  source_domain TEXT NOT NULL,
  symbols TEXT, categories TEXT,          -- comma-joined
  sentiment TEXT, sentiment_score REAL,   -- filled Phase 4
  fetched_at TEXT NOT NULL, processed_at TEXT,
  metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_domain, fetched_at);
CREATE TABLE IF NOT EXISTS seen_articles (
  hash TEXT PRIMARY KEY, title_norm TEXT, source_domain TEXT, seen_at REAL
);
```
Pragmas on every connection: `journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`.
**Single-writer:** scrapers never touch DB directly; they `writer.enqueue(article)`; `DBWriter` thread drains queue, batches ≤50/txn (`BEGIN IMMEDIATE`), `INSERT ... ON CONFLICT(url) DO NOTHING`. `writer.stop()` flushes queue → graceful shutdown.

**Domain config schema (`config/domains/<name>.yaml`):**
```yaml
name: cafef
enabled: true
method: api            # api | rss | html
fallback: null         # optional secondary method
rate_limit: 3.0
timeout: 30
api: {endpoint: "...", http_method: GET, params: {...}, headers: {...}}
rss: {feeds: [{url: "...", name: "..."}]}
html: {selectors: {title: "...", body: "...", date: "..."}}
pitfalls: "free-text notes"
```

## Related Code Files
**Create:** `src/core/__init__.py`, `src/core/models.py`, `src/core/base_scraper.py`, `src/core/config.py`, `src/core/logging.py`, `src/db/writer.py`, `config/settings.yaml`, `config/watchlist.yaml`, `config/secrets.yaml.example`, `config/domains/` (dir), `tests/test_store.py`, `tests/test_base_scraper.py`
**Modify:** `src/db/store.py` (schema v2 + WAL), `src/db/dedup.py` (SQLite-backed), `src/crawler/http_client.py` (logger, 3.0s), `src/processor/pipeline.py` (use core.models.Article), `src/run_collection.py` (de-Hermes wording; thin wrapper until Phase 6 orchestrator), `config/collections.yaml` (drop telegram targets → `to: local`; drop tech_blogs/cmt_research or mark enabled:false), `README.md` (full rewrite), `docs/architecture.md` (remove ClickHouse), `requirements.txt` (+loguru, beautifulsoup4, requests-cache, tenacity, apscheduler), `.gitignore` (+config/secrets.yaml, logs/, data/*.db*)
**Delete:** `skills/web-monocle-cron.md`, `skills/web-monocle-rss.md`, `scripts/deploy_crons.sh`, `scripts/financial_collector.py` (replace with `scripts/run_once.py` standalone), `data/dedup_cache.json` (after migration)

## Implementation Steps
1. Baseline: run `python -m pytest tests/ -x` — record pass/fail before touching anything.
2. Create `src/core/logging.py`: `setup_logging(level="INFO")` → loguru sink `logs/monocle.log`, rotation "50 MB", retention "14 days", plus stderr sink. Call once at entry point.
3. Create `src/core/models.py`: `@dataclass Article` with fields per schema above + `to_row()` / `from_row()`; `@dataclass ScrapeResult(scraper, fetched, new: list[Article], errors: list[str])`. Keep `sha256_hash(url, title)` helper here (single source of truth for dedup hash).
4. Create `src/core/config.py`: YAML loaders with defaults; `load_domain_config("cafef")` reads `config/domains/cafef.yaml`; raise clear error listing missing keys.
5. Rewrite `src/db/store.py`: `_connect()` applies 3 pragmas; `init_schema()` DDL above; `insert(article) -> bool` (True if new row via `cursor.rowcount`); `get_recent`, `count_by_domain(since)` for metrics.
6. Create `src/db/writer.py`: `DBWriter(store)` daemon thread; `enqueue(article)`; internal loop: drain up to 50 items or 2s timeout → single txn; `stop(flush=True)` joins thread. Register `atexit` + `signal.SIGINT/SIGTERM` handler in entry point → graceful shutdown.
7. Rewrite `src/db/dedup.py`: `DedupCache(store)` backed by `seen_articles` table; keep API `is_duplicate(url, title)`, `mark_seen(url, title, source_domain)` (now stores `title_norm` = lowercased, diacritic-preserved, whitespace-collapsed title for Phase 4 fuzzy); `cleanup(max_age_days=30)`; one-time migration: import hashes from `data/dedup_cache.json` if present, then delete file.
8. Create `src/core/base_scraper.py` per Architecture pseudocode; `run()` wraps each abstract call in try/except → append to `self.errors`, never raise out (graceful degradation, spec §4.3).
9. Update `src/crawler/http_client.py`: `rate_limit_delay=3.0` default; `print` → `logger.warning`; add `get_json()` and `post_json()` helpers (P3 needs POST).
10. Refit `src/processor/pipeline.py` to consume/produce `core.models.Article` (delete local Article class); replace prints with logger.
11. De-Hermes sweep: `Grep -i hermes` across repo → fix every hit. Delete files listed above. Create `scripts/run_once.py`: `python scripts/run_once.py [scraper_name|all]` standalone entry.
12. Rewrite `README.md`: actual tree only, SQLite-only architecture diagram, quick start (`pip install -r requirements.txt`, `python scripts/run_once.py all`), no Telegram/ClickHouse/Hermes. Update `docs/architecture.md` same.
13. Update `requirements.txt` + `.gitignore` per list above. `pip install -r requirements.txt` verify on Windows.
14. Tests: `tests/test_store.py` (WAL active — assert `PRAGMA journal_mode` returns `wal`; UNIQUE url conflict ignored; writer thread flush on stop), `tests/test_base_scraper.py` (dummy subclass: dedup skip works, error in parse_item doesn't crash run()). Fix any baseline test broken by refactor.

## Todo List
- [ ] Baseline existing tests
- [ ] core/logging.py (loguru)
- [ ] core/models.py (Article, ScrapeResult, sha256_hash)
- [ ] core/config.py (settings/domain/watchlist/secrets loaders)
- [ ] db/store.py schema v2 + WAL pragmas
- [ ] db/writer.py single-writer queue + graceful shutdown
- [ ] db/dedup.py SQLite-backed + JSON migration
- [ ] core/base_scraper.py ABC
- [ ] http_client.py: 3.0s default, logger, post_json
- [ ] pipeline.py refit to core models
- [ ] De-Hermes sweep (grep, delete skills/scripts, collections.yaml)
- [ ] scripts/run_once.py standalone entry
- [ ] README + architecture.md rewrite
- [ ] requirements.txt + .gitignore
- [ ] tests/test_store.py + tests/test_base_scraper.py green

## Success Criteria
- `grep -ri hermes` → 0 hits (excl. `thamkhao/`, `plans/`).
- `PRAGMA journal_mode` returns `wal`; kill -9 during write leaves DB readable.
- Dummy scraper subclass runs end-to-end: fetch → dedup → enqueue → row in `articles` with `content_html` + `content_text` populated.
- Zero `print()` in `src/` (logger only). README describes only files that exist.
- All tests pass: `python -m pytest tests/ -v`.

## Risk Assessment
- **Schema migration breaks old data:** old `articles` table incompatible → keep old DB as `data/articles_v1.db` backup; fresh v2 DB (article volume is low, acceptable loss per MVP status).
- **Windows file locking on WAL (-wal/-shm files):** antivirus/indexer can lock — document exclusion of `data/` dir; busy_timeout mitigates.
- **Over-abstraction (YAGNI):** BaseScraper limited to 3 hooks; no plugin registry/metaclass magic — registry is plain dict in Phase 6 orchestrator.
- **underthesea heavy install on Windows:** defer to Phase 4; not in Phase 1 requirements.txt.

## Security Considerations
- `config/secrets.yaml` gitignored; `secrets.yaml.example` with placeholder keys only (fireant_token). Never log token values.
- SQL: parameterized queries only (already pattern in store.py).
- Logs may contain URLs — no credentials in URLs for Phase 1 sources; keep it that way.

## Next Steps
Phase 2 — implement `CafeFScraper(BaseScraper)` as first concrete proof of the abstraction.
