---
id: FACT-cleanup-moves-data-to-archive
type: fact
title: Cleanup moves data to archive, never deletes
status: active
created: 2026-09-24
updated: 2026-10-06
verified: 2026-10-05
lang: en
authors: [claude-opus-5-5]
adr: [ADR-0020]
evidence:
  - "path: docs/decisions/0020-data-plane-sharepoint-co-che-xuat-ban.md"
  - "path: plans/20260924-1627-codebase-audit-cleanup-modularization"
  - "operator: 2026-10-05 old data moved to archive with MANIFEST.txt, not deleted"
summary: Data that looks like junk can be the only Bronze copy, so cleanup MUST move it to C:\data\news-scape\archive or recovered, never delete it.
---

# FACT-cleanup-moves-data-to-archive — Cleanup moves data to archive, never deletes

## Fact

- The 2026-09-24 audit found 767 raw HTML files and 237 articles in `project/src/data/` that existed nowhere else.
- It also found 163 articles unique to `project/data/monocle.db`. They looked like junk but were the only Bronze copy.
- Old data now sits in `C:\data\news-scape\archive\20261005-cleanup\` with a `MANIFEST.txt`.
- The legacy `C:\data\news-scape\raw_html` was not yet moved on 2026-10-05.
- `Research-FPA/news-scraper` is the private organization repo (remote `fpa`). Local branch `import/clean-20261005` is the clean history snapshot.
- Old history holds analyst subscription xlsx files, so it MUST NOT be pushed. The operator pushes, because agent sessions lack push rights on the organization repo.
- `FRA - Data` is the teamsite `fptscomvn.sharepoint.com/sites/FRA/Data`, attached by OneDrive shortcut with cloud-only Files On-Demand.
- The repo folder itself is the teamsite `sites/FRA_DataIngestion`. ADR-0020 (proposed) covers one-way, append-only publishing with a manifest.

## Why

- A dead-code cleanup agent once listed `src/data` as "safe to delete".
- Deleting it would have destroyed the only copy of those Bronze articles.

## How to Apply

- Cleanup MUST move data into `C:\data\news-scape\archive\` or `C:\data\news-scape\recovered\` after operator approval, never delete.
- Continue development on branches cut from `fpa/main`.
