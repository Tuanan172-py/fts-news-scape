---
id: FACT-capture-everything-dedupe-later
type: fact
title: Capture everything, deduplicate later
status: active
created: 2026-10-01
updated: 2026-10-06
verified: 2026-10-01
lang: en
authors: [claude-opus-5-5]
adr: [ADR-0013]
evidence:
  - "path: .agents/rules/10-thu-thap-tron-ven.md"
  - "path: project/src/core/base_scraper.py"
  - "operator: 2026-10-01 pinned: fetch every article, no filtering at the scrape layer, duplicates are signal"
summary: The scrape layer fetches every article the source has; dedup and cleaning come after Bronze, never delete, and duplicates keep source and time because frequency is a signal.
---

# FACT-capture-everything-dedupe-later — Capture everything, deduplicate later

## Fact

- The scrape layer fetches as many articles as the source has.
- It does not filter by similarity, section or relevance, and does not stop hard at page 1.
- Dedup and cleaning run after Bronze and never delete an article.
- A confirmed duplicate is exempt from the LLM and inherits the original's result.
- It keeps every source and timestamp, because frequency and breadth of coverage are a sentiment signal.

## Why

- Measured on 2026-10-01: fuzzy filtering in `base_scraper` wrongly dropped 202 of 439 articles over 3 days.
- baodautu held only about 50% of the articles listed in its sitemap.
- The operator treats repeated publication across sources as an investment signal.

## How to Apply

- Every scrape-layer change MUST follow `.agents/rules/10-thu-thap-tron-ven.md` and ADR-0013: discovery ledger, watermark and sitemap reconciliation.
- Every anti-duplicate design MUST group into clusters, never delete.
- See FACT-copy-threshold-and-cluster-pitfalls for the copy threshold.
