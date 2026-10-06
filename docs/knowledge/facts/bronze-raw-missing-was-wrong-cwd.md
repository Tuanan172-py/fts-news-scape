---
id: FACT-bronze-raw-missing-was-wrong-cwd
type: fact
title: Bronze raw_missing was a wrong cwd
status: active
created: 2026-10-05
updated: 2026-10-06
verified: 2026-10-05
lang: en
authors: [claude-opus-5-5]
adr: []
story: [US-035]
evidence:
  - "path: project/src/crawler/raw_store.py"
  - "path: project/scripts/capture_reconcile.py"
  - "commit: d38714b"
summary: The raw_missing articles of 2026-09-28 to 2026-10-02 were Bronze files written under the repo root data folder by a process with the wrong cwd, not lost data.
---

# FACT-bronze-raw-missing-was-wrong-cwd — Bronze raw_missing was a wrong cwd

## Fact

- 1,241 articles flagged as lost Bronze actually sat in `<repo root>/data/raw_html`.
- A process with the repo root as cwd wrote through a relative path.
- They were merged into `project/data/raw_html` on 2026-10-05.
- 1,607 files with the same name and different content are kept in `C:\data\news-scape\recovered\root_raw_html_conflicts_20261005`.
- The DB was backed up first to `C:\data\news-scape\monocle.db.bak-20261005-pre-bronze-merge`.
- `RawStore` now resolves data paths through the project root (US-035; paths later routed through `core.paths`).

## Why

- `RawStore` wrote relative to cwd while `derive` read relative to `PROJECT_ROOT`.
- The `silver_failures` key was not normalized, so old failure rows pinned the watermark at 2026-09-25.
- A failed capture once overwrote the meta of a good capture (fireant 41948083).

## How to Apply

- MUST NOT run `capture_reconcile.py recapture` while the file still exists on disk.
- First match `silver_failures` against disk under every root.
- A long-running morninger keeps old code in memory. After a scrape-layer change it must be restarted, which needs the operator because stopping the process is blocked.
