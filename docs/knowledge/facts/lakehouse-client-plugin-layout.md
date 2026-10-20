---
id: FACT-lakehouse-client-plugin-layout
type: fact
title: Unified plugin layout for Lakehouse client consumption
status: active
created: 2026-10-20
updated: 2026-10-20
verified: 2026-10-20
lang: en
authors: [antigravity]
adr: [ADR-0025]
evidence:
  - path:docs/decisions/0025-unified-plugin-architecture-for-lakehouse-consumption.md
  - path:project/src/lakehouse/
  - metric:DuckDB vectorized scan 2905 articles in 0.42s
summary: Defines standard directory layout and zero-config path discovery for the fpts-market-intel plugin across AGY and Gemini.
---

# FACT-lakehouse-client-plugin-layout — Unified plugin layout for Lakehouse client consumption

## Fact

- Client-side Lakehouse querying capabilities are packaged as a single plugin at `~/.gemini/config/plugins/fpts-market-intel/`.
- The plugin bundle contains `plugin.json`, `rules/AGENTS.md`, `skills/`, and shared Python tooling in `tools/lakehouse_client.py`.
- Path discovery resolves OneDrive shortcuts via a three-tier sequence: environment variable `$env:NEWS_DATA_ROOT`, standard shortcut paths, and filesystem scan for `_manifest/latest.json`.
- DuckDB executes in-memory against canonical Parquet partitions (`parquet/articles/year=YYYY/month=MM/part-YYYYMMDD.parquet`) using array filtering `list_contains(symbols, '...')`.
- Scanning over 2,900 articles consumes 0.42 seconds and zero LLM input tokens.

## Why

- Distributing loose individual skills causes version divergence across analyst machines.
- Duplicating DuckDB connection and path discovery scripts violates the DRY principle and increases maintenance costs.
- Analysts require zero-config onboarding through pre-built `suggestedPrompts` on the IDE interface.

## How to Apply

- Distribute updates only via the unified `fpts-market-intel` plugin repository or archive.
- Do not create independent standalone skills in `~/.gemini/config/skills/` for Lakehouse querying.
- Invoke DuckDB queries exclusively through `tools/lakehouse_client.py` across all bundled skills.
