---
id: US-049
type: story
title: Research codebase architecture and decide on module restructuring
status: implemented
lane: high-risk
created: 2026-10-22
updated: 2026-10-22
lang: en
authors: [claude-opus-5-5]
branch: dev/us049-codebase-modularization
adr: [ADR-0027]
plan: []
related: [PRP-20261022-codebase-modularization, RULE-12, ADR-0010, ADR-0024]
evidence:
  - commit:ec4e7fe
  - commit:eaff01f
  - commit:b0acee2
  - commit:b50077b
  - commit:5b3a2c5
  - commit:cfe8ceb
  - commit:b8e37d7
  - commit:4d4d5d5
  - path:docs/proposals/20261022-codebase-modularization.md
  - path:plans/20260924-1627-codebase-audit-cleanup-modularization/plan.md
  - test:project/tests/repo/test_architecture.py
  - test:project/tests/article_lane/test_lane_golden.py
  - "metric:project/scripts 78 files and 14,922 LOC at ec4e7fe, 37 files and 4,451 LOC after; 10,490 LOC of dead code deleted"
  - "metric:pytest project 934 passed (898 plus 36 merged from US-048), 1 known failure, 0 skipped; root tests 31 passed"
verify: "cd project && python -m pytest tests/repo/test_architecture.py tests/article_lane/test_lane_golden.py -q"
summary: Lane logic moved from flat scripts into layered src packages behind unchanged CLI paths, dead code removed, and an ast test with shrink-only allowlists now blocks new boundary violations.
---

# US-049 — Research codebase architecture and decide on module restructuring

## Contract

- The codebase MUST follow ADR-0027: logic in `project/src` by layer, thin CLIs at unchanged paths under `project/scripts`, tests mirroring `src` packages.
- Every CLI path that Task Scheduler, `.agents/pipeline.yaml`, conductor programs and runbooks call MUST keep working with the same output.
- `pytest tests/repo/test_architecture.py` MUST fail on any new boundary violation; its allowlists only shrink.

## Acceptance Criteria

- [x] Import graph and reachability measured from the live entry points; options decided in PRP-20261022-codebase-modularization (operator 2026-10-22: option B).
- [x] S1: architecture test with frozen allowlists, golden snapshots of packet, conductor program and expand output.
- [x] S2: 58 dead files deleted (retired L1/Gold lane, applied migrations, unused manual tools); dead symbols trimmed from `l1_runner`, `l1_router`, `batch_handoff`, `runner`, `pruner`; script inventory test.
- [x] S3: `PROJECT_ROOT`, `REPO_ROOT`, `harness_db_path()` only in `src/core/paths.py`; SQLite connections through `src/db/connect.py`.
- [x] S4: lane logic in `src/article_lane/` and `src/ops/`; no `scripts → scripts` or `src → scripts` import; `trace`, `pipeline_spec`, `redact`, ops config moved below `src/ops`, removing seven cyclic package edges.
- [x] S5: `src/ops/{wave,runtime,console}`, `src/agent/{runners,contract,ingest,catalog,packet}`; 100 tests in `tests/<package>/`.
- [ ] Merge into `dev/us038` in a quiet window and restart the daemon (operator action, `docs/OPEN-ITEMS.md`).

## Design Notes

- Kept on purpose: `project/scripts/doc_lint.py` (live through `test_doc_lint.py`) and `maintenance/migrate_users_output.py` (US-045 migration not run; 607 files remain in `C:\data\news-scape\users_output`).
- Remaining allowlisted cycles: `core ↔ db`, `core ↔ crawler`, `agent ↔ handoff`, `export ↔ lakehouse`; one `src` module still edits `sys.path` (`src/morninger.py`).
- Not changed: `project/schemas/article-compact-v2.schema.json` keeps an old path in its description, because the schema feeds the cached prefix.
- Hand-off to US-046: 59 documents under `project/docs`, `okf` and `project/domains` still name deleted scripts or old module paths.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python -m pytest tests/repo/test_architecture.py tests/article_lane/test_lane_golden.py -q` | pass |
| Integration | `python -m pytest tests --ignore=tests/repo/test_cli_entrypoints.py -q` in `project/` | 934 passed (898 plus 36 diagram tests merged from US-048), 1 failed (`test_ops_council_fixes.py::test_b2_sensor_does_not_count_reserved_articles`, failing since `ec4e7fe`), 0 skipped |
| Integration | `python -m pytest tests -q` at the repository root | 31 passed |
| Platform | `article_run.py --where` and `pipeline_radar.py status` compared with the canonical tree | identical apart from the capture age in minutes |

## Evidence

- Commits in frontmatter; proposal and ADR-0027 record the decision; RULE-12 states the operating checks.
