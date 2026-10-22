---
id: US-044
type: story
title: Analyst use-case skills for fpts-market-intel plugin
status: implemented
branch: dev/us038
lane: normal
created: 2026-10-20
updated: 2026-10-20
lang: en
authors: [operator, agent]
adr: [ADR-0025]
plan: []
evidence: []
verify: "C:\\venvs\\news-scape\\Scripts\\python.exe -m pytest project/tests/repo/test_plugin_lakehouse_client.py project/tests/repo/test_plugin_manifest.py -q -p no:cacheprovider"
summary: Analysts on the Fundamental, Market/Technical, Macro and Morning desks get twelve plugin skills backed by zero-token DuckDB lenses that filter by entity, group duplicate articles into stories and compare against baselines.
---

# US-044 — Analyst use-case skills for fpts-market-intel plugin

## Contract

The `fpts-market-intel` plugin must cover the research desk's everyday news EDA use cases. Every skill follows one pattern: subject (ticker, sector, theme) plus time window plus question. A deterministic DuckDB lens filters, counts and compares against a baseline at zero LLM tokens; the LLM only interprets a compact, cited evidence pack. Tickers are selected through entities, not the sparse `symbols` column (FACT-lakehouse-symbols-column-is-sparse-filter-tickers-by).

## Acceptance Criteria

- [x] `lakehouse_client.py` builds `articles` (with `pub_date`, `story_key`, `sent_score`, `is_hot`) and `article_entities` views and tolerates missing Parquet columns.
- [x] Lenses `timeline`, `window`, `buzz`, `pulse`, `themes`, `cooccur`, `brief`, `lookup` exist as methods and CLI subcommands returning JSON with baseline/coverage disclosure.
- [x] `query_ticker` matches `entities` or `symbols`; `query` serializes list columns to JSON.
- [x] Skills: ticker-timeline, catalyst-tracker, sector-impact (Fundamental); buzz-radar, sentiment-pulse (renamed from sector-pulse), price-explainer (Market/Technical); macro-timeline, theme-trend, geo-link (Macro); daily-brief three tiers (Morning); ticker-screener and lakehouse-explorer updated.
- [x] `config/themes.json` holds analyst-editable themes defined by entity ids and keywords.
- [x] `rules/AGENTS.md` requires separating measured from interpreted output and disclosing baseline sufficiency.
- [x] 23 plugin tests pass, including a test that every `python $LH <cmd>` in a SKILL.md is a valid subcommand.

## Design Notes

- Plugin-only change under ADR-0025; no change to the Lakehouse data contract or to `project/src`.
- Stories are grouped by normalized title inside DuckDB; this is consumer-side counting and does not replace `article-processor` recognition (AGENTS.md section 7.3).
- Buzz z-score uses the previous N days with data, zero-filled per entity, with a 0.5 standard-deviation floor (same floor as `project/src/analytics/signals.py`).
- Theme velocity divides by the days a window actually overlaps the data, and reports `Chưa đủ lịch sử` while data covers seven days or less.
- The sandbox held four days (2026-10-16..19) at implementation time; the operator publishes the full history separately.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `pytest project/tests/repo/test_plugin_lakehouse_client.py project/tests/repo/test_plugin_manifest.py -q` | 23/23 PASS |
| Integration | `pytest project/tests -q` | 953 PASS, 3 FAIL outside plugin scope (`test_code_first_guard` publisher import, `test_daily_reporter`, `test_ops_council_fixes`) |
| Platform | Every lens CLI run against the sandbox `FRA_DataIngestion - news-data` | PASS (JSON output) |

## Evidence

- `path:plugins/fpts-market-intel/tools/lakehouse_client.py`
- `path:plugins/fpts-market-intel/skills/`
