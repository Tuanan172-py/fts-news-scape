---
id: FACT-dsh-worker-session-token-accounting
type: fact
title: DSH worker session token accounting
status: active
created: 2026-09-23
updated: 2026-10-06
verified: 2026-09-23
lang: en
authors: [claude-opus-5-5]
adr: [ADR-0010]
evidence:
  - "path: project/scripts/token_ledger.py"
  - "path: project/scripts/article_run.py"
  - "wave: W365"
summary: DSH worker sessions are bare-uuid checkpoints identified by identity.createdAt, so wave token figures MUST come from token_ledger append --workers-only, not from mtime or preset filters.
---

# FACT-dsh-worker-session-token-accounting — DSH worker session token accounting

## Fact

- A DSH worker checkpoint has a bare uuid id with no `session-` prefix and `turn=1`.
- A worker inherits the parent preset (`news-scape-conductor`), so the preset cannot tell worker and conductor apart.
- `identity.createdAt` in milliseconds is the creation mark. Filtering by mtime pulls the long-lived conductor session into the wave.
- Use `token_ledger append --workers-only`.
- Real W365 worker numbers: about 2,850 tokens per article, 1 turn, cache hit per batch about the prefix size (about 10K). A hit rate near 9% is normal.
- The earlier figures of 25,628 tokens per article and 89.8% cache came from mixing in the conductor session.
- Before 2026-09-23, `ingested: done/failed` summed the whole folder, including 85 old L1 files that failed the schema. `--finish` now passes only the wave's files.
- The DSH sandbox cannot extend `writableRoots()` beyond the workspace root and temp. `--finish` and delivery need `danger-full-access`; the guard sits only at `--finish`.

## Why

- Wrong numbers (25,628 tokens per article, L1 failed=123, a COMPLETE banner on an empty DB) led the W365 review to wrong conclusions.
- Putting the write guard at the prepare step would block every wave.

## How to Apply

- When reading wave numbers, trust the post-check table and ledger rows with note `workers-only`.
- Treat wave numbers recorded before 2026-09-23 as suspect.
- Coverage is read from the post-check table, not from ingest counters.
