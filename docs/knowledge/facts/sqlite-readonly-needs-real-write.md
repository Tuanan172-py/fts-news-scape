---
id: FACT-sqlite-readonly-needs-real-write
type: fact
title: SQLite read-only detection needs a real write
status: active
created: 2026-09-23
updated: 2026-10-06
verified: 2026-09-23
lang: en
authors: [claude-opus-5-5]
adr: []
evidence:
  - "path: project/scripts/article_run.py"
  - "wave: W365"
summary: BEGIN IMMEDIATE succeeds on a read-only SQLite file, so a write probe MUST perform a real write such as CREATE TABLE and then ROLLBACK.
---

# FACT-sqlite-readonly-needs-real-write — SQLite read-only detection needs a real write

## Fact

- `BEGIN IMMEDIATE` still succeeds on a read-only SQLite file.
- Only a real write, such as `CREATE TABLE` followed by `ROLLBACK`, reveals that the database is not writable.
- Windows PowerShell 5.1 swallows double quotes inside `python -c` arguments.

## Why

- A probe that only opens a transaction reports the DB as writable.
- The wave then spends tokens and fails at ingest, or reports completion on an empty DB, as seen around W365.

## How to Apply

- Any DB-writable check, such as `article_run.py --where`, MUST perform a real write and roll it back.
- Run Python one-liners through the Bash tool, not PowerShell 5.1.
