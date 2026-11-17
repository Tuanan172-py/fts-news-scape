---
id: FACT-lakehouse-client-cost-is-view-building-not-parquet
type: fact
title: Lakehouse client cost is view building, not Parquet scanning
status: active
created: 2026-11-17
updated: 2026-11-17
verified: 2026-11-17
lang: en
authors: [agent]
adr: [ADR-0033]
evidence:
  - path:plugins/fpts-market-intel/tools/lakehouse_pit.py
  - "metric: production 56,710 rows: count over read_parquet 0.31 s, client init 3.79 s, materialize 5.63 s (2026-11-17)"
  - "metric: before cache status 5.5 s, buzz 11.0 s, pulse 14.8 s, themes 15.1 s; cache hit 0.9 s, 2.2 s, 2.3 s, 7.7 s; cache build 20.7 s"
summary: On the production lakehouse a raw Parquet scan takes 0.3 s while building views and keyword columns takes about 9 s, so plugin speed comes from caching built tables, not from rollup files.
---

# FACT-lakehouse-client-cost-is-view-building-not-parquet — Lakehouse client cost is view building, not Parquet scanning

## Fact

- On 916 production partitions (56,710 rows, OneDrive) a `count(*)` over `read_parquet` takes 0.31 s.
- `NewsLakehouseClient` init takes 3.79 s (intraday delta merge, `NOT IN` dedup, views) and `_materialize()` takes 5.63 s (`search_text` folding and entity parsing).
- The local cache of ADR-0033.D6 brings `status` from 5.5 s to 0.9 s and `buzz` from 11.0 s to 2.2 s.
- It brings `pulse` from 14.8 s to 2.3 s and `themes` from 15.1 s to 7.7 s; building the cache once costs about 21 s.

## Why

- Optimizing file layout (rollups, compaction, Z-order) does not touch the 9 s that matter and adds files the production `verify()` must whitelist.

## How to Apply

- Before optimizing a lens, time `init`, `_materialize()` and the lens query separately.
- Remaining `themes` time is keyword matching per theme; optimize that query, not storage.
- Any change to the view SQL invalidates the cache automatically, because the key includes the client source files.
