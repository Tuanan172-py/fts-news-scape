---
id: US-030
type: story
title: Harness git governance and session closure gate
status: implemented
lane: normal
created: 2026-10-01
updated: 2026-10-06
lang: en
authors: [An Pham Thanh, claude-opus-5-5]
adr: []
plan: []
evidence:
  - commit:1561636
  - commit:de34143
  - commit:0340f64
  - path:scripts/harness_cli.py
  - path:scripts/schema/004-git-tracking.sql
  - path:scripts/git_hooks/pre-commit
  - path:docs/GIT_COMMIT_STANDARD.md
  - path:.agents/skills/git-codebase-governance/SKILL.md
  - path:.agents/rules/04-harness-durable-invariants.md
  - test:tests/test_harness_cli.py
  - metric:pytest tests/test_harness_cli.py -k git, 2 passed, 7 deselected, 2026-10-01
verify: "python -m pytest tests/test_harness_cli.py -k git -q"
original: "commit:1561636"
reconstructed: 2026-10-06
summary: The harness records branch and commit on stories and traces, offers git checkpoint, verify, status and template commands, and blocks session closure and commits while the tree is dirty or invalid.
---

# US-030 — Harness git governance and session closure gate

## Contract

After this story, the harness knows which git branch and commit each story and trace belongs to. Agents commit through a mechanical Conventional Commits template, and a session cannot be called closed while the working tree is dirty.

## Acceptance Criteria

- [x] Schema migration `004-git-tracking.sql` adds `git_commit` and `git_branch` to the `story` and `trace` tables.
- [x] `harness_cli.py` detects the current branch and latest commit and stores them on every trace.
- [x] `story complete --commit` creates a `type(scope): title (US-XXX)` commit after the verification gate and stores its hash.
- [x] `harness_cli.py git checkpoint|verify|status` exist; `git template` prints a commit message of at most 72 characters.
- [x] `.gitignore` excludes `scratch/`, `openrouter/*_key.py` and `**/test_scratch*.py`; the stray `.kilo/worktrees/pushy-cheddar` worktree is removed.
- [x] Rule 04 adds git to the Harness Closure table; the `git-codebase-governance` skill ties commit, push and PR to a story.
- [x] A pre-commit hook runs `harness_cli.py git verify` and rejects the commit on failure (commit labelled US-036, see Evidence).
- [x] `AGENTS.md` section 11 and rule 01 section 7 forbid closing a session while `clean_for_closure` is false.

## Design Notes

- Problem before this story (reconstructed from the original Vietnamese file): stories reached `implemented` without a matching commit, with US-028 as the cited case.
- Scratch files such as `test1.py` and `check_key.py` sat untracked and risked being staged by mistake.
- Parent epic in `harness.db`: "Harness Core Governance". Intake id 28.
- The closure gate of commit 0340f64 is harness governance by content, so it belongs here even though its subject carries US-036.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python -m pytest tests/test_harness_cli.py -k git -q` | 2 passed, 7 deselected (harness.db evidence, 2026-10-01) |
| Integration | `harness_cli.py git status` reports `clean_for_closure` | used as the closure gate in later sessions |
| Platform | pre-commit hook runs `git verify` on every commit | installed in commit 0340f64 |

## Evidence

- Commit 1561636: git lifecycle in `harness_cli.py`, schema 004, rule 04, governance skill and tests. `harness.db` stores it as the story commit.
- Commit de34143: `docs/GIT_COMMIT_STANDARD.md` and the `git template` command with tests.
- Commit 0340f64 (commit labelled US-036): session closure gate in rule 01 section 7, `AGENTS.md` section 11 and `scripts/git_hooks/pre-commit`.
- ADR-0002 Context cites migration 004 and commit 1561636 for this story.
