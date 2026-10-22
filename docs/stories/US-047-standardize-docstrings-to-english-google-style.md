---
id: US-047
type: story
title: Standardize docstrings to English Google style
status: implemented
branch: dev/us038
lane: normal
created: 2026-10-21
updated: 2026-10-21
lang: en
authors: [agent]
adr: []
plan: []
evidence: []
verify: "cd project && python -m pytest tests/test_cli_entrypoints.py -q"
summary: Every public module, class and function in project/src and project/scripts carries an English Google-style docstring, enforced by an AST linter and a phrase scanner.
---

# US-047 — Standardize docstrings to English Google style

## Contract

Docstrings and comments in `project/src` and `project/scripts` are written in English imperative Google style (AGENTS.md §8, ADR-0021.D4). Public entities have a docstring whose `Args:`, `Returns:`, `Yields:` and `Raises:` sections match the signature. Code behaviour, signatures, SQL and delivered Vietnamese user output stay untouched.

## Acceptance Criteria

- [x] AST linter on `project/src` and `project/scripts`: 100% coverage, 0 `MISSING_DOCSTRING`. Two accepted false positives: `ops/breakers.py` `Breakers.record` (classmethod receiver named `cls`, `EXTRA_PARAM`) and `scripts/l1_route.py` `main` (nested generator, `MISSING_YIELDS`).
- [x] Phrase scanner (`.agents/rules/banned_phrases.json`) reports 0 ERROR and 0 WARNING on both trees.
- [x] AST of every touched file is identical to the original once docstrings are stripped (208 files, 0 differing).
- [x] `pytest tests/` shows no new failure (known baseline: `test_b2_sensor_does_not_count_reserved_articles` fails before this story).

## Design Notes

Adopts the external skill `codebase-docstring-refactoring` selectively: linter and scanner are used from the skill path, the dictionary is a repo-local copy. Tests are out of scope. Scripts that pass `__doc__` to `argparse` keep a first line that survives `splitlines()[0]`. Rule update: `.agents/rules/06-code-and-docstring-standards.md`.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python -m pytest tests/ -q` | 999 pass, 1 known fail (baseline 965 pass, 1 known fail; other tests added by US-048) |
| Integration | AST-equality over touched files vs HEAD | 208 checked, 0 differing |
| Platform | piped run of `pipeline_radar.py status`, `article_run.py --where`, `--help` of signal_build, requeue, capture_reconcile, provider_conformance | exit 0, no traceback |

## Evidence

Linter coverage before -> after: src 93.0% (654/720 functions) -> 100% (720/720); scripts 81.8% (167/218) -> 100% (222/222).
