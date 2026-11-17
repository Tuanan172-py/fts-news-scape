---
id: US-052
type: story
title: Multi-scope NER provenance, normalized entity DB and two-speed skill workflow
status: planned
lane: high-risk
created: 2026-11-12
updated: 2026-11-13
lang: en
authors: [agent]
adr: [ADR-0031]
plan: []
evidence:
  - path:docs/decisions/0031-multi-scope-entity-provenance-and-skill-workflow.md
verify: "C:/venvs/news-scape/Scripts/python.exe -m pytest project/tests/test_ner_entity_db_v2.py -q"
summary: Retain title, body and inferred entities with role and provenance in the normalized entity database, eliminate scraper symbol noise, and add fast intraday delta reads plus priority queueing for skills.
---

# US-052 — Multi-scope NER provenance, normalized entity DB and two-speed skill workflow

## Contract

Analysts and pipelines receive verified title, body and inferred entities with explicit `role` and `provenance` free of scraper symbol noise. Skill queries read local intraday deltas and queue priority refreshes asynchronously.

## Acceptance Criteria

- [x] `tickers.yaml` has zero duplicate keys. `build_entities.py` rejects duplicate YAML keys, classifies `E12` as `STOCK`, and builds `UNLISTED_ORG` entries from `unlisted_orgs.yaml`.
- [x] `EntityRegistry` guards two-word diacritic-stripped matches, covers all 27 listed bank prefixes for `PGD`, and disambiguates `BTC` by context.
- [x] `IntentResolver`, `article_expand.py` and `check_l1_dod` (`l1_output_version = "1.1"`) resolve `TIC` across security types and normalize corporate prefixes on `COM`. Multi-scope entities retain `role`, `provenance` and `first_para_idx`.
- [x] `news_research_master.db` stores `scope`, `role`, `provenance`, `confidence_tier` and `first_para_idx` in `article_entities` and logs `entity_candidates_log`. Parquet exports emit accurate `intent_*` columns, and `user_output.py` routes `role = 'primary'` by default.
- [x] `lakehouse_client.py` isolates raw `symbols` on enriched rows, defaults to `role = 'primary'` with `--include-mentions`, and fixes the 3-character ticker trap. It also supports accent-insensitive search, SQL file-read guards, read-only intraday delta union, and `request-refresh` signals for `ops_daemon`.

## Design Notes

- Implements ADR-0031 (D1 through D5) while keeping `article-compact-v2` single-turn LLM output unchanged (ADR-0010, ADR-0017) so zero extra tokens are spent.
- Preserves backward compatibility with legacy `l1_output_version = "1.0"` records and existing Parquet `[TYPE]` entity tags.
- All unit and integration tests run against temporary SQLite and Parquet directories in accordance with `FACT-tests-must-not-write-operational-db`.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `C:/venvs/news-scape/Scripts/python.exe -m pytest project/tests/test_ner_entity_db_v2.py -q` | 7 passed |
| Integration | 10-suite regression (`test_ner_entity_db_v2`, `test_entities`, `test_article_lane`, `test_l1_router`, `test_l1_runner`, `test_research_production`, `test_publisher`, `test_user_output`, `test_plugin_lakehouse_client`, `test_ops_core`) + `harness_cli.py doc lint --summary` | 200 passed, 0 doc errors |
| Platform | Real subprocess CLI execution of `lakehouse_client.py request-refresh` with UTF-8 piped stdio + `scan_code_phrases.py` (0 errors/warnings) | pass |

## Evidence

- `docs/decisions/0031-multi-scope-entity-provenance-and-skill-workflow.md` accepted by operator on 2026-11-12.
