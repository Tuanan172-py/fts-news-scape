---
id: ADR-0031
type: adr
title: Multi-scope entity provenance database and two-speed skill workflow
status: accepted
lane: high-risk
created: 2026-11-12
updated: 2026-11-12
lang: en
authors: [agent]
approvers: [operator]
story: [US-052]
supersedes: []
amends: [ADR-0005, ADR-0010, ADR-0025]
evidence:
  - path:project/scripts/article_expand.py
  - path:project/src/agent/intent_resolve.py
  - path:project/src/research_db/master.py
  - path:plugins/fpts-market-intel/tools/lakehouse_client.py
  - "operator: 2026-11-12 approved NER assessment and Entity Database optimization plan"
summary: Preserve title, body and inferred entities with role and provenance in a normalized entity database, isolate noisy scraper symbols, and run a two-speed CQRS workflow for analyst skills.
summary_vi: Bảo toàn thực thể tiêu đề, thân bài và ngành suy luận kèm vai trò, xuất xứ trong CSDL chuẩn hóa và tách luồng đọc ghi hai tốc độ cho skill phân tích.
---

# ADR-0031 — Multi-scope entity provenance database and two-speed skill workflow

## Context

- `article_expand.py` previously filtered `resolved` entities to `in_title` substrings before building `l1-entity-output`, discarding every body entity and inferred industry emitted by `article-processor`.
- `IntentResolver` looked up `TIC` only under `TICKER:` (missing `ETF:` and `SECURITY_OTHER:`) and matched `COM` by exact folded equality, failing when articles added legal prefixes.
- `tickers.yaml` contained four duplicate YAML keys (`VIC`, `MWG`, `VPB`, `MSN`) that overwrote earlier brand aliases, while `build_entities.py` classified 3-character stock `E12` as `ETF:E12`.
- `lakehouse_client.py` unioned `entities` with raw scraper `symbols` (contaminating `TICKER:HCM` with Ho Chi Minh City tags), forced every unknown 3-character query into `TICKER:*`, and lost `BOTH`, `LLM_ONLY` and `CODE_ONLY` provenance.
- Passive publishing ran on fixed slots with a multi-hour gap for non-urgent watchlist news, whereas synchronous scraping inside analyst skills would block queries and contend for locks.

Code inspection confirmed that the LLM already reads full article paragraphs in one turn, so entity loss and false positives originated in deterministic post-processing, storage serialization and query resolution rather than model capacity.

## Decision

1. **ADR-0031.D1 — Multi-scope entity contract (`l1_output_version = "1.1"`):** `l1-entity-output` MUST retain resolved entities across `scope` values `title`, `body` and `inferred`, carrying `role` (`primary` or `mentioned`), `provenance` (`BOTH`, `LLM_ONLY` or `CODE_ONLY`) and `first_para_idx`. `check_l1_dod` MUST validate `title` substrings for `scope == "title"`, paragraph substrings when paragraphs are supplied for `scope == "body"`, and catalog membership for `scope == "inferred"`.
2. **ADR-0031.D2 — Catalog hygiene and unlisted organizations:** `build_entities.py` MUST reject duplicate YAML keys, classify 3-character equity codes as `STOCK` unless listed in `etf_codes`, and support curated `UNLISTED_ORG` entries with optional `parent_entity_id` links. `EntityRegistry` MUST enforce diacritic safety on short two-word Vietnamese aliases, cover all listed bank prefixes in the `PGD` guard, and disambiguate `BTC` by fiscal versus crypto context.
3. **ADR-0031.D3 — Normalized Entity Database and candidate rollup:** `news_research_master.db` MUST store `scope`, `role`, `provenance`, `confidence_tier` and `first_para_idx` on `article_entities` with an index on `(entity_id, role, provenance)`, and MUST aggregate unlisted mentions into `entity_candidates_log` for reviewed catalog growth.
4. **ADR-0031.D4 — Provenance export and scraper symbol isolation:** Parquet exporters MUST compute `intent_llm`, `intent_code` and `intent_source` from per-entity `provenance` and encode `[TYPE|ROLE|PROVENANCE]` tags. `lakehouse_client.py` MUST NOT union raw scraper `symbols` for enriched articles and MUST default ticker and brief lenses to `role = 'primary'` with an opt-in `--include-mentions` flag.
5. **ADR-0031.D5 — Two-speed CQRS workflow:** Analyst skills MUST stay zero-token, lock-free readers attaching `news_research_master.db` read-only (`?mode=ro`) for intraday delta rows. Skills enqueue asynchronous priority requests in `ops.db` instead of scraping live, while `ops_daemon` fast-tracks Tier-1 waves during trading hours and syncs `news_research_master.db`.

## Alternatives

| Option | Why rejected |
|---|---|
| Patch YAML and regexes only while keeping `l1_output_version = "1.0"` | Retains the `surface in title` gate, continuing to drop all body-only tickers and inferred industries from `l1_outputs` and Parquet exports. |
| Add a second dedicated NER model and run live scraping inside skill calls | Duplicates inference maintenance without addressing deterministic resolver drops, risks HTTP 429 limits, and stalls interactive analyst queries for minutes. |

## Consequences

- Body tickers and inferred industries already extracted by `article-processor` reach `news_research_master.db`, Excel delivery (`role = 'primary'`) and Parquet lenses at zero extra LLM token cost.
- Filtering by `role = 'primary'` and isolating raw `symbols` eliminates Ho Chi Minh City false positives on `TICKER:HCM` and keeps analyst briefs free of passing single-mention noise.
- `lakehouse_client.py` resolves accent-insensitive Vietnamese keywords, avoids the 3-character ticker trap on unknown codes, blocks file-reading DuckDB functions in `query --sql`, and reads local intraday delta rows without locking `monocle.db`.
- Existing `v1.0` rows remain valid: missing `scope`, `role` and `provenance` default to `title`, `primary` and `BOTH` during reads.

## Rollback

- Revert the `US-052` commit on the working branch and rebuild affected Parquet partitions from `news_research_master.db`. The operator authorizes any rollback touching production partitions.

## Follow-up

- [x] Implement `US-052` across catalog, resolver, expander, `research_db`, `ops_daemon` sensor and `lakehouse_client.py` with automated unit and CLI tests.
- [ ] Run `build_entities.py` against `FRA - Data` on the operator machine to materialize `UNLISTED_ORG` entries and updated aliases into `entities.json`.
