---
id: FACT-tests-must-not-write-operational-db
type: fact
title: Tests must not write the operational DB
status: active
created: 2026-09-24
updated: 2026-10-06
verified: 2026-10-06
lang: en
authors: [claude-opus-5-5]
adr: []
evidence:
  - "path: project/tests/test_cli_entrypoints.py"
  - "path: plans/20260924-1627-codebase-audit-cleanup-modularization"
summary: The full pytest run writes DDL to the operational DB through test_cli_entrypoints.py, and simulated wave output once landed in it, so tests and simulations MUST use a temporary DB.
---

# FACT-tests-must-not-write-operational-db — Tests must not write the operational DB

## Fact

- `project/tests/test_cli_entrypoints.py` runs `backfill_deferred --dry-run` without passing a DB.
- That writes DDL and WAL to `C:\data\news-scape\monocle.db`. Found in the 2026-09-24 audit; the test still passes no DB on 2026-10-06.
- On 2026-09-18 simulated wave output was loaded into the operational DB by mistake.
- It was cleaned; the backup is `C:/data/news-scape/monocle.db.bak-20260918T172336`.

## Why

- A child agent wrote to the real DB by running pytest.
- Simulated data in the operational DB corrupts coverage and delivery.

## How to Apply

- MUST NOT ask an agent to run the full `pytest tests/` until S0 of the audit plan is done.
- Run `pytest tests --ignore=tests/test_cli_entrypoints.py` instead.
- To test a chain end to end, point it at a temporary DB, never the real one.
