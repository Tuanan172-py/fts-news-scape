---
id: US-057
type: story
title: ADR-0027 and the entity catalog on FRA - Data news
status: implemented
branch: m1/us057-adr0027
lane: high-risk
created: 2026-11-23
updated: 2026-11-23
lang: en
authors: [agent]
adr: [ADR-0027, ADR-0030, ADR-0031, ADR-0034]
plan: [PLN-20261123-1510-production-upgrade-to-article-compact-v3-and-sync]
evidence:
  - "commit: ece8f62, f85eba4, cfb4115, fb365a1"
  - "metric: replay 4,665 research rows, 27,960 CODE_ONLY ids removed, 0 rows and 0 model-named ids lost"
  - "wave: W11231849, W11231900 (first two waves after the 2026-11-23 18:05 restart)"
verify: "C:/venvs/news-scape/Scripts/python.exe -m pytest project/tests/test_lakehouse_model_entities.py project/tests/test_ner_entity_db_v2.py project/tests/test_article_lane_hardening.py project/tests/test_research_production.py -q"
summary: The entities column on FRA - Data/news carries only ids the model named, the article prefix is rebuilt from the live catalog, and the catalog is published with its SHA-256.
---

# US-057 — ADR-0027 and the entity catalog on FRA - Data news

## Contract

Users reading FRA - Data/news through skills see in `entities` only ids the model named; ids only the deterministic matcher found stay in `intent_code`. The article prefix pair matches the live catalog, and the catalog itself is published next to the partitions with its SHA-256 in the manifest.

## Acceptance Criteria

- [x] The ADR-0027 file set from fpa-toolkit `main` is copied whole (plan P2 inventory).
- [x] `research_db/production.py` applies `keep_model_entities` to `entities`.
- [x] The HSG test reads HSG through `intent_code` and not through `include_mentions`, without xfail; ADR-0031.D4 is amended.
- [x] `--check-prefix` is green on prefix files rebuilt from the live `entities.json`.
- [x] The research publisher writes `entities.json` and its SHA-256 into the manifest.
- [x] Replay: no lost row and no lost model-named id.

## Design Notes

Plan PLN-20261123-1510, phases P2, P3, P4 and P6. Decisions D1, D9, D10. The research path does not call `sanitize_article_record`, so the copied `ingest.py` alone does not reach FRA - Data/news.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `verify` command above | |
| Integration | replay report (P3) | |
| Platform | P6: two waves DONE, 0 partition errors to end of 2026-11-25 | |

## Evidence

- Port `ece8f62`; HSG test and ADR-0034 `f85eba4`; prefix `cfb4115` (hash `80c6edfe7891330b`, equal to `main`); catalog publish `fb365a1`.
- The research path reaches `keep_model_entities` through `records_to_parquet_bytes`, so no change to `day_records` was needed (plan P3 task 2).
- Live on `dev/us038` `31a5ad4` since 2026-11-23 18:05:45. Partition 2026-11-23 on FRA - Data/news: 458 rows, 0 `CODE_ONLY`. Six research publishes to the end of the day, all with 0 partition errors.
- Verify: 56 passed.
