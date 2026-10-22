# HARNESS_BACKLOG.md — Friction reservoir (news-scape)

The harness grows from friction. When something is hard / repeats / is ambiguous / lacks a rule → record it with `python scripts/harness_cli.py backlog add` (don't silently change the process).

**Risk** = a lane (`tiny` / `normal` / `high-risk`), not `low`.

| # | Title | Discovered while | Current pain | Suggested improvement | Risk | Status |
|---|-------|------------------|--------------|-----------------------|------|--------|
| 1 | Status not queryable across stories | Building TEST_MATRIX by hand | Proof/status lived in a hand-edited markdown table + scattered story files. | H2: SQLite `story`/`trace` + `harness-cli query matrix`. | normal | **resolved**: `python scripts/harness_cli.py query matrix` |
| 2 | WIP=1 has no enforcement | Writing the WIP=1 rule | Honor-system only; nothing stopped two `in_progress` stories. | Lint check on a single `in_progress` per branch. | tiny | **resolved**: `doc lint` code K13 and `audit` check 2 (`wip_by_branch` in `scripts/knowledge.py`, ADR-0022) |
| 3 | SESSION-LATEST is live-state in markdown | Wiring step-9 handoff | A hand-edited state file drifts if not overwritten every session. | Fold into durable `trace.next_action`; keep the file as a generated view. | tiny | open |
| 6 | Normal-lane context budget too tight for audit work | Recording the US-011 trace | `score_context` counted files read by Explore subagents, penalising the delegation the rule encourages. | Scope the ceiling to files that enter the orchestrator's context directly. | normal | **resolved** (US-014) |
| 7 | Broken local `project/.venv` | Running pytest for US-011 | Pointed at the Python 3.14 of a renamed Windows profile; violated the no-local-`.venv` rule. | Delete the folder (destructive, needs confirmation). | tiny | **obsolete**: no `project/.venv` exists in `C:\src\news-scraper`; the venv is `C:\venvs\news-scape` (ADR-0024) |
| 8 | `harness_cli intake`: argparse 9 types, DB CHECK 6 types | Recording intake for US-015 | `qa_inquiry`/`diagnostic`/`exploration` were valid per FEATURE_INTAKE.md §1 but rejected by the CHECK constraint. | Widen CHECK to all 9 types. | tiny | **resolved**: `scripts/schema/003-intake-types.sql` |

> **From H2 on, the source of truth is the `backlog` table in `harness.db`** (`harness_cli.py backlog add/close`).
> This markdown table is a quick-read snapshot; items #4 and #5 live only in the DB.

<!-- On close: add "Outcome:" with the actual measured result. -->
