# Scout 01 — DB + Pipeline internals

## Tables (project/src/db/store.py)
- **articles** (~L53): url, title, summary, content_html, content_text, published_at, author, source_domain, symbols, categories, sentiment, sentiment_score, fetched_at, processed_at, metadata_json. PK/hash: `url_title_hash` (see `get_by_hash`). NOTE: article_id used elsewhere == this hash — VERIFY exact column name at impl time.
- **work_items** (~L118): article_id, raw_sha256, domain, package_path, status, claimed_by, claimed_at, done_at, error, change_state, enqueued_at.
- **agent_outputs** (~L137): article_id, raw_sha256, work_item_id, output_json, agent_provider, model_used, confidence, dod_pass, dod_reasons, created_at.
- **l1_tasks** (~L160, article_id UNIQUE): article_id, domain, title, code_first_json, route, packet_path, status, enqueued_at, done_at, error.
- **l1_outputs** (~L175, article_id UNIQUE): article_id, output_json, recognized, agent_provider, model_used, confidence, dod_pass, dod_reasons, created_at.
- **pipeline_state** (~L153): exists; used for run bookkeeping (confirm columns at impl).

## ArticleStore methods
- `connect()` L220 (WAL). `get_by_hash()` L224.
- `get_l1_task(article_id)` L353; `get_l1_output(article_id)` L386; `insert_l1_output(row)` L372; `set_l1_status(...)`; `upsert_l1_task(...)`.
- `get_agent_output(article_id, raw_sha256)` L289; `insert_agent_output(row)` L301.
- No per-user / user_assignments table exists (greenfield).

## Join for "both layers done"
```
articles a
  JOIN l1_outputs   l1 ON l1.article_id = a.<id>  AND l1.dod_pass=1
  JOIN agent_outputs ao ON ao.article_id = a.<id> AND ao.dod_pass=1
```
Both output_json blobs hold the layer fields (parse JSON at read).

## csv_export.py
- Columns: fetched_at, published_at, source_domain, symbols, categories, sentiment, sentiment_score, title, summary, url.
- `query_rows(db_path, today, days, domains, with_symbols, limit)` L36; `write_csv(rows, out_path)` L62 (utf-8-sig, Excel-safe); `export(...)` L78 → (Path, count).
- Filter is domain/date only — NO per-user filter. Reusable for `write_csv` + utf-8-sig; needs new per-user query joining l1/agent outputs.

## agent-output-v1 field paths (schema + dod.py)
Required: output_schema_version, article_id, summary.abstractive, implication.text, materiality.score(0..1), confidence(0..1), citations[]{claim, source_span, source_offset}, processing_metadata{agent_provider, model_used, timestamp}.
Optional: sentiment.overall(-1..1), sentiment.polarity(neg/neu/pos), event_type(enum), extraction_quality(high/med/low), entities.companies[]{name,ticker,sentiment}.
`check_dod` (dod.py ~L65): schema_valid, confidence≥0.65, ≥2 citations w/ source_span⊂cleaned_text & len≥20, extraction_quality∈{high,medium}, metadata complete.

## l1-entity-output-v1 field paths
Required: l1_output_version, article_id, title, recognized(bool), entities[]{surface⊂title, type, method, in_list}, categories{ticker_company, etf_fund, index, exchange, industry_sector}∈{done,none,out_of_list}, citations[]{source_span⊂title}, confidence(≥0.60), processing_metadata.
`check_l1_dod` (l1_router.py ~L94): schema + grounding(surface/span⊂title) + consistency(recognized⇒entities≥1 & citations≥1) + category coherence + confidence≥0.60 + metadata.

## Pipeline flow
- Orchestrator `project/src/orchestrator.py` `run_cycle(names)` L87 — scrapers → classify/sentiment → DBWriter → `_export_csv()` today. `--once` single cycle.
- Stages `project/src/pipeline/run.py` `process_meta()` L36: bronze(raw_html) → silver(SilverBuilder trafilatura) → version(change_detect state NEW/UNCHANGED/CONTENT_CHANGED/TEMPLATE_DRIFT/SELECTOR_BROKEN) → work-package(WorkPackageBuilder + schema) → Catalog.enqueue() work_items pending/held.
- L1: `scripts/l1_route.py` (route_and_export → l1_tasks + packets data/agent_tasks/l1/) → `scripts/l1_ingest.py` (ingest_output → validate+DoD → status).
- Agent: `scripts/agent_export.py` / `scripts/agent_ingest.py` (AgentRunner). 
- Config `project/src/core/config.py` L19/L52: db path from config/settings.yaml default `data/monocle.db`.

## Unresolved
- Exact article PK column name (url_title_hash vs article_id) — verify at impl.
- pipeline_state columns.
- No user/owner concept anywhere (greenfield).
