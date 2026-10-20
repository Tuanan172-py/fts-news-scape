---
id: FACT-lakehouse-symbols-column-is-sparse-filter-tickers-by
type: fact
title: Lakehouse symbols column is sparse, filter tickers by entities
status: active
created: 2026-10-20
updated: 2026-10-20
verified: 2026-10-20
lang: en
authors: [agent]
adr: [ADR-0025]
evidence:
  - path:plugins/fpts-market-intel/tools/lakehouse_client.py
  - metric:symbols non-empty in 241 of 2905 sandbox articles (2026-10-16..19)
summary: The OBT symbols column covers about 8% of articles and disagrees with entities, so plugin lenses select tickers through the article_entities view that unions both columns.
---

# FACT-lakehouse-symbols-column-is-sparse-filter-tickers-by — Lakehouse symbols column is sparse, filter tickers by entities

## Fact

- In the sandbox Lakehouse (2,905 articles, 2026-10-16 to 2026-10-19) the `symbols` list is non-empty for only 241 articles (about 8%).
- `symbols` and `entities` disagree: articles carry `TICKER:BID [TICKER]` in `entities` while `symbols` is empty or lists other tickers.
- `entities` items have the form `KIND:CODE [LABEL]`; observed kinds are `TICKER`, `MACRO_GEO`, `MACRO_THEME`, `ASSET_CLASS`, `IND_GICS1/2/3`, `INDEX`, `INSTITUTION`, `EXCHANGE`.
- `lakehouse_client.py` builds the view `article_entities(article_id, entity_id, kind)` from both columns (label suffix stripped, `symbols` mapped to `TICKER:<code>`); every ticker, sector and macro lens filters through it.

## Why

- Filtering with `list_contains(symbols, ...)` silently drops most articles about a ticker, so timelines, buzz z-scores and briefs undercount.

## How to Apply

- In plugin SQL, select by `article_entities.entity_id` (for example `TICKER:HPG`), never by `symbols` alone.
- When the exporter or the article contract changes `symbols` or `entities`, re-measure coverage and update this fact.
