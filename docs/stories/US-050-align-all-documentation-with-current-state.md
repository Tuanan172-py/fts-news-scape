---
id: US-050
type: story
title: Align all documentation with the current project state
status: implemented
lane: normal
created: 2026-10-22
updated: 2026-10-22
lang: en
authors: [claude-opus-5-5]
branch: dev/us049-codebase-modularization
adr: [ADR-0027, ADR-0028]
plan: []
related: [US-046, US-049, ADR-0010, ADR-0024, ADR-0026]
evidence:
  - path:docs/proposals/20261022-codebase-modularization.md
  - path:docs/decisions/0028-retire-manual-opencode-batch-script.md
  - test:project/tests/article_lane/test_code_first_guard.py
  - "metric:reference scanner over live documents: 796 hits in 119 files before, 161 justified hits in 45 files after"
  - "metric:29 documents archived to project/docs/archive and okf/archive; okf_check 45 ok, 0 stale"
  - "metric:pytest project 944 passed, 1 known failure; root tests 31 passed; doc lint 0"
verify: "python scripts/harness_cli.py doc lint"
summary: Every live document, rule, skill and code comment names only files, commands and decisions that exist after US-049, and documents about retired subjects move to an archive with a pointer to their replacement.
---

# US-050 — Align all documentation with the current project state

## Contract

- Live documents are AGENTS.md, harness docs, facts, rules, skills, registry, runbooks, design, dev, okf and READMEs.
- No live document tells a reader to run a deleted tool, use a removed flag, open a moved file at its old path, or follow a superseded decision.
- A live document whose main subject is retired moves to `project/docs/archive/` or `okf/archive/` with a first-line notice and a link to its replacement; inbound links follow.
- History stays as written: `plans/`, `docs/proposals/`, `docs/runs/`, closed stories, changelogs and accepted ADR bodies (K-R8).

## Acceptance Criteria

- [x] The reference scanner reports no unexplained broken path, command or link in live documents (remaining 161 hits are prohibitions, removal notes, history sections and reference copies).
- [x] `harness_cli doc lint` reports 0 findings and `doc index` is regenerated.
- [x] ADR-0026.D3's reference to the deleted `opencode_native_run.py` is amended by ADR-0028.
- [x] Facts re-verified; FACT-tests-must-not-write-operational-db marked `stale` (conftest isolates the data root).
- [x] Code drift found by the sweep fixed: the live One Big Table publish path leaked code-first entities (ADR-0010 D4, US-040); the guard test now covers the live path.

## Design Notes

- Continues the remaining scope of US-046 after the US-049 restructuring; US-046 belongs to the `dev/us038` worktree and is not edited here.
- `project/docs/diagrams/` is excluded because another session edits it in the canonical tree; only one map node that pointed to an archived file changed.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python scripts/harness_cli.py doc lint` | 0 findings |
| Unit | `python -m pytest tests/article_lane/test_code_first_guard.py -q` in `project/` | red before the publisher fix, green after |
| Integration | `python -m pytest tests -q` in `project/`; `python -m pytest tests -q` at the root | 944 passed, 1 known failure (`test_b2_sensor_does_not_count_reserved_articles`); 31 passed |
| Integration | `okf/tools/okf_check.py outdated` | 45 ok, 0 stale |

## Evidence

- Archived documents keep their sub-path under `project/docs/archive/` and `okf/archive/`; each starts with a notice naming its replacement.
- Open operator questions: opencode in the daemon `PROVIDERS`, US-039 status, GLOSSARY language and legacy tables in `store.py`.
- Also open: the `rss_generic` filter that runs before the discovery ledger, and the DSH sandbox mode for wave preparation.
