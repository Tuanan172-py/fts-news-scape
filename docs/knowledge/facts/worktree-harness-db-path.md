---
id: FACT-worktree-harness-db-path
type: fact
title: Worktrees need the canonical harness.db path
status: active
created: 2026-10-22
updated: 2026-10-22
verified: 2026-10-22
lang: en
authors: [claude-opus-5-5]
adr: [ADR-0024, ADR-0022]
evidence:
  - path:scripts/harness_cli.py
  - "operator:2026-10-22 session close in C:/src/news-scraper-us049 failed with 'no such table: story'"
summary: "harness.db is gitignored, so a new worktree has none and harness_cli creates an empty one; set NEWS_SCAPE_HARNESS_DB to C:/src/news-scraper/harness.db before session close."
---

# FACT-worktree-harness-db-path — Worktrees need the canonical harness.db path

## Fact

- `harness.db` is gitignored. In a fresh worktree `scripts/harness_cli.py` opens `<worktree>/harness.db`, creates an empty file and fails with `no such table: story` on `session close`.
- The authoritative database is `C:/src/news-scraper/harness.db` (ADR-0024.D5). `harness_cli.py` reads its path from `NEWS_SCAPE_HARNESS_DB`.

## Why

- Without the variable the trace goes nowhere, and a stray empty `harness.db` stays in the worktree.

## How to Apply

- In any worktree other than `C:/src/news-scraper`, run harness commands with `NEWS_SCAPE_HARNESS_DB=C:/src/news-scraper/harness.db` (PowerShell: `$env:NEWS_SCAPE_HARNESS_DB = "C:/src/news-scraper/harness.db"`).
- Delete an empty `harness.db` the CLI created in the worktree.
