---
id: US-051
type: story
title: Unified documentation lifecycle and contract governance
status: in_progress
lane: high-risk
branch: dev/us038
created: 2026-10-23
updated: 2026-10-23
lang: en
authors: [claude-opus-5-5]
adr: [ADR-0029, ADR-0021]
plan: []
related: [US-039, US-046]
evidence:
  - path:docs/decisions/0029-unified-documentation-lifecycle.md
  - path:plans/20261008-0923-us039-handoff-remaining-work/plan.md
  - "operator: 2026-10-23 unified documentation lifecycle tracking story across waves W-A through W-F"
verify: "python -m pytest tests/test_knowledge.py tests/test_harness_cli.py -q"
summary: Every tracked markdown file belongs to one document class with one writer and one check, one linter and one story-status writer remain, and each topic has one canonical document.
---

# US-051 — Unified documentation lifecycle and contract governance

## Contract

After this story an agent or operator who adds or edits any markdown file gets one class, one command and one commit-time check for it. Story status changes in one place and reaches the file, the database and the index together. Each topic has one canonical document, and other files on the topic point to it.

## Acceptance Criteria

- [x] W-A: ADR-0029 accepted with approvers; this story `in_progress` on `dev/us038`; stale `id:` lines removed from `legacy.txt`; US-046 implemented; US-039 set to `changed` with its remaining work packages moved here.
- [ ] W-B: schema version 2 with types `reference`, `ledger`, `skill`, `okf`; codes K14 to K22 implemented with one test each in `tests/test_knowledge.py`; `project/scripts/doc_lint.py` deleted and its cases ported.
- [ ] W-C: `knowledge.set_story_status` is the only status writer. `story update`, `story complete` and `session close` call it. `hooks install` writes the dispatcher. `doc index --check` exists, and `audit` reports `hook_installed` and status drift.
- [ ] W-D: every tracked markdown file is classified or exempt with a reason; 12 rules and 22 plans migrated; ADR-0020 and US-041 governed; `legacy.txt` deleted.
- [ ] W-E: canonical topics from ADR-0029.D14 applied with pointer files; harness hub pages in `docs/` English; SESSION-LATEST and OPEN-ITEMS agree with active facts.
- [ ] W-F: no retired term in a live document; tool-private plans in `plans/`; `lint.warn` empty; this story closed through `session close`.

## Design Notes

- Branch `dev/us038` is the active line for this documentation unification milestone.
- Absorbs the open work packages W2 to W9 and W11 of PLN-20261008-0923-us039-handoff-remaining-work and open sweep from US-046.
- Never run `pytest tests/` inside `project/`; run named files only. Never start the daemon, a wave or DSH.
- Skill and OKF frontmatter is never edited (ADR-0029.D5).

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python -m pytest tests/test_knowledge.py tests/test_harness_cli.py -q` | pending |
| Integration | `python scripts/harness_cli.py doc lint` and `doc index --check` | pending |
| Platform | commit on a branch without the in-tree hook passes the dispatcher | pending |

## Evidence

- ADR-0029 accepted 2026-10-23 by operator.
