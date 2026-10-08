---
id: FACT-copy-threshold-and-cluster-pitfalls
type: fact
title: Copy threshold and clustering pitfalls
status: active
created: 2026-10-02
updated: 2026-10-06
verified: 2026-10-02
lang: en
authors: [claude-opus-5-5]
adr: [ADR-0013, ADR-0016]
evidence:
  - "path: project/scripts/story_cluster.py"
  - "path: project/scripts/capture_reconcile.py"
  - "path: project/scripts/signal_build.py"
  - "path: project/src/core/urlnorm.py"
  - "commit: bfbd5e6"
  - "commit: fb9b1c2"
summary: Only exact duplicates or containment of at least 0.95 with the same figures and tickers become copy and inherit results; measured clustering pitfalls need best-neighbor joins and a 40-shingle floor.
---

# FACT-copy-threshold-and-cluster-pitfalls — Copy threshold and clustering pitfalls

## Fact

- Deployed in US-033: `discovered_urls` and `url_aliases` keyed by source article id via `src/core/urlnorm.py`.
- Also deployed: `capture_reconcile.py` (reconcile, backfill, recapture, status), `story_cluster.py` with `inherit.py` and `cluster_job.refresh`, `signal_build.py` and the attention radar sheet.
- Morninger runs catch-up capture after capture, then clustering and signals after derive.
- Label `copy` only for exact duplicates or containment of at least 0.95 with the same figures and tickers. Inherited results carry the original's verbatim citations.
- A 0.8 rewrite is a `candidate` and still gets full analysis.
- Pitfall: transitive merging by ticker chained 10 PNJ events into one cluster. Fix: join the best neighbor only, never union everything.
- Pitfall: boilerplate-only articles give a false containment of 1.0. Require at least 40 shingles.
- Pitfall: dated recurring columns MUST NOT merge; forbid merging when the two titles carry different dates.
- `ama_z` inflates because of the 0.5 standard deviation floor. Always read it with article count, source count and `coverage_pct`.

## Why

- Session-start measurements on 2026-10-02: cafef missed 64% against its sitemap, tnck 68%, baodautu 44%.
- A wrong `copy` label silently gives an article another article's citations.

## How to Apply

- Open items that each need a separate decision: P3 divergence mode, I3 price reconciliation, I5 advertising flag.
- When stopping a child process inside a background command chain, the parent shell still runs the next command. Check with `Get-CimInstance Win32_Process` before trusting that it stopped.
- See FACT-capture-everything-dedupe-later and FACT-tests-must-not-write-operational-db.
