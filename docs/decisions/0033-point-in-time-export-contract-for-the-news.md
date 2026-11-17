---
id: ADR-0033
type: adr
title: Point-in-time export contract for the news lakehouse
status: accepted
lane: high-risk
created: 2026-11-17
updated: 2026-11-17
lang: en
authors: [agent]
approvers: [operator]
story: [US-055]
supersedes: []
amends: [ADR-0030]
evidence:
  - path:project/src/lakehouse/ingest.py
  - path:project/src/research_db/production.py
  - path:project/src/research_db/master.py
  - path:project/src/ops/probes.py
  - path:plugins/fpts-market-intel/tools/lakehouse_pit.py
  - path:plugins/fpts-market-intel/config/trading_calendar.json
  - test:project/tests/test_pit_export.py
  - test:project/tests/test_plugin_pit.py
  - "metric: published_at length 25 for 57,249 of 57,320 operational articles; 569 carry 00:00:00 (2026-11-17)"
  - "metric: 38,815 articles hold a story cluster row in monocle.db (2026-11-17)"
  - "metric: plugin status 5.5 s, buzz 11.0 s, pulse 14.8 s, themes 15.1 s on 56,710 production rows before the cache (2026-11-17)"
summary: Production Parquet gains capture time, timestamp precision, analysis time and story cluster columns, the manifest gains a freshness block, and the plugin derives available_at, a holiday-aware trade_date, a cutoff filter and a local cache.
summary_vi: Parquet production bổ sung giờ thu thập, độ chính xác giờ đăng, giờ phân tích và mã cụm câu chuyện; manifest có khối độ tươi; plugin tính available_at, trade_date theo lịch nghỉ, lọc theo mốc cắt và có cache cục bộ.
---

# ADR-0033 — Point-in-time export contract for the news lakehouse

## Context

- The production OBT (ADR-0030) exports `published_at` and `updated_at` only; the capture time `fetched_at` exists in `monocle.db` and in the master but never reaches Parquet.
- Without capture time a query "what was known at 10:15" cannot exclude an article published at 10:05 but captured at 11:40, so every intraday or backtest use has look-ahead bias.
- 569 operational articles carry a source time of exactly `00:00:00`, meaning the source gave only a date; lenses currently treat them as morning news.
- Story clusters (ADR-0016) exist for 38,815 articles in `monocle.db`, yet the plugin groups stories by a normalized title, so rewritten headlines of one event count as separate stories.
- `trade_date` in the plugin skips weekends but not exchange holidays, so news before Tet or 30/4 maps to a closed session.
- Plugin sessions rebuild every view per command: 5.5 s for `status` and 11 to 15 s for `buzz`, `pulse` and `themes` on 56,710 rows. A raw Parquet scan takes only 0.3 s, so the cost is view building and keyword columns.
- A crawler that silently yields fewer articles is not detected: `zero_articles` fires only on an empty run.
- The two-speed design of US-052 has no push channel for urgent model-labelled stories; analysts poll.

## Decision

1. D1: The production OBT MUST append `first_seen_at` (capture time), `published_at_precision` (`datetime`, `date`, `missing`) and `analyzed_at` (analysis time) at the end of `LAKEHOUSE_ARTICLE_SCHEMA`. Readers MUST fill NULL for partitions written before, which the manifest marks as `obt_schema` `obt/1`.
2. D2: The master MUST mirror story cluster membership (`article_story`) from `monocle.db` on every sync, and the OBT MUST carry `story_id`, `story_role` and `story_n_sources`. A change of membership or source count MUST queue the day partition for rewrite.
3. D3: The plugin MUST compute `available_at = greatest(published_at, first_seen_at)` and MUST apply `--cutoff` on `available_at` only. `trade_date` MUST use `config/trading_calendar.json`; a year that is absent or not verified MUST raise a warning in `status`.
4. D4: The daemon MUST run a per-source yield probe that compares the last 120 minutes with the same window of the 10 previous weekdays. It runs on weekdays from 08:00 to 17:00 and uses a Poisson floor for the deviation.
5. D5: The production manifest MUST carry `obt_schema`, `columns` and a `freshness` block (newest publication, capture and analysis times, date-only share, captured but unpublished articles of the last 48 hours).
6. D6: The plugin CLI SHOULD keep the materialized tables in a local DuckDB cache outside synced folders. The key covers partition files, the intraday master, the client code, the calendar and the cutoff. A cache error MUST fall back to building views.
7. D7: After each successful production publish the daemon SHOULD queue one Telegram alert listing stories that the model labelled `urgent`, grouped by `story_id`, captured within the last 12 hours. No keyword rule MAY select an article (AGENTS.md section 7.3).

## Alternatives

| Option | Why rejected |
|---|---|
| Streaming MinHash at ingest with containment 0.65 to inherit labels | FACT-copy-threshold-and-cluster-pitfalls measured that only containment of at least 0.95 with equal figures keeps inherited citations correct; clusters already exist and only need export. |
| Compute `available_at` from `updated_at` | `updated_at` is the analysis or publish time, later than capture, so it would hide articles that were known. |
| Publisher-side rollup Parquet files | They add files that `verify()` must whitelist and every lens must learn; the measured cost is client view building, which a local cache removes without changing the shared folder. |
| Sub-60-second hot path from unlabelled captures | Labels come from waves and readers see Parquet through OneDrive sync; an alert on unlabelled text would need a keyword classifier, which AGENTS.md section 7.3 forbids. |
| Regex PR filter in the plugin | ADR-0032 adds a model-produced event kind instead. |

## Consequences

- Gains: point-in-time queries without look-ahead, stories counted by cluster and holiday-correct sessions.
- Gains: on a cache hit `status`, `buzz` and `pulse` run under 2.5 s and `themes` in 7.7 s (production, 2026-11-17).
- Gains: silent source decay raises a warning, and urgent stories reach Telegram at each publish.
- Costs: the first publish after deployment rewrites nearly every day partition because every story row is new, which causes one large OneDrive sync.
- Costs: the first plugin command after a data change takes about 21 s to build the cache.
- Risk: the holiday list is compiled from decrees and marked `verified: false`; `status` warns until an operator checks the HOSE notices. Mitigation: weekend-only fallback outside listed years.
- Risk: `story_n_sources` changes as copies arrive, so recent day partitions are rewritten more often; this is bounded by the publish slots.

## Rollback

- Revert the commit of US-055. Readers keep working because every new column is optional and filled with NULL; the operator may republish with `research_publish.py --rebuild` to drop the columns, and set `research_publish.urgent_alerts: false` and remove `probes.yield` in `ops.yaml` to stop alerts.

## Follow-up

- [x] The 2024 to 2026 holiday lists were checked on 2026-11-17 against the HOSE notices of 2023-12-07, 2024-04-19, 2024-12-26 and 2025-12-09; 2026 gained 2026-01-02 and 2026-08-31, which the decree-based list missed.
- [ ] Add 2027 when HOSE publishes its notice, usually in December.
- [x] After the first publish, re-measure `pit_coverage` in plugin `status`: on 2026-11-17 `first_seen_share` is 1.0 and `story_share` 0.679, because story clusters cover only articles clustered since ADR-0016.
- [ ] Update plugin lens SKILL.md files to prefer `--cutoff` for intraday questions and `story_key` for counts.
