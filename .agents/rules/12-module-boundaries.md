---
id: RULE-12
type: rule
title: Module boundaries
status: active
created: 2026-10-22
updated: 2026-10-22
lang: en
trigger: always_on
adr: [ADR-0027]
summary: Business logic lives in project/src by layer, project/scripts holds thin CLIs at stable paths, and an ast test blocks new boundary violations.
---

# RULE-12 — Module boundaries

## Scope

- Every change to Python code under `project/src/`, `project/scripts/` and `project/tests/`, by any agent or human.
- Decision and rationale: ADR-0027. This rule states the operating checks only.

## Rules

1. **RULE-12.R1 (Layers).** `src/core` (L0) and `src/db` (L1) MUST NOT import domain packages. Domain packages MUST NOT form import cycles at top-level package granularity.
2. **RULE-12.R2 (Thin CLIs).** A file under `project/scripts/` MUST only parse arguments and call a function in `src`. New logic goes into the owning package: lane logic in `src/article_lane/`, wave and operator logic in `src/ops/{wave,runtime,console}/`, agent work in `src/agent/{runners,contract,ingest,catalog,packet}/`.
3. **RULE-12.R3 (Stable paths).** Existing CLI paths MUST NOT move or be renamed; Task Scheduler, `.agents/pipeline.yaml`, conductor programs and runbooks call them.
4. **RULE-12.R4 (Forbidden edges).** No `scripts → scripts` import and no `src → scripts` import.
5. **RULE-12.R5 (Plumbing).** Code roots come from `src.core.paths` (`PROJECT_ROOT`, `REPO_ROOT`, `harness_db_path()`). SQLite connections outside `src/db` internals go through `src.db.connect.open_ro` or `open_rw`.
6. **RULE-12.R6 (Inventory).** A new script MUST be declared with its caller in `SCRIPT_INVENTORY`; a script no live entry point calls is deleted, not kept "in case".
7. **RULE-12.R7 (Tests mirror src).** A new test goes into `project/tests/<package>/`; repository-wide checks go into `project/tests/repo/`.

## Verification

- `python -m pytest tests/repo/test_architecture.py -q` from `project/` checks R1, R4, R5 and R6. Its allowlists may only shrink; a fixed violation fails the test until its entry is removed.
- `python -m pytest tests/article_lane/test_lane_golden.py -q` proves that a move did not change packets, conductor programs or expand outputs.
