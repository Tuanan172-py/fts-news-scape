---
id: PLN-20261008-0923-us039-handoff-remaining-work
type: plan
title: US-039 handoff, remaining knowledge framework work
status: executing
lane: high-risk
created: 2026-10-08
updated: 2026-10-08
lang: en
authors: [claude-sonnet-5-5]
adr: [ADR-0021, ADR-0022]
story: [US-039, US-040]
evidence:
  - commit:c7e7de2
  - commit:8442636
  - path:docs/knowledge/README.md
  - path:docs/knowledge/schema.yaml
  - path:docs/knowledge/legacy.txt
  - "operator: 2026-10-06 answered Q1-Q4, ruled DSH never retired, WIP=1 per worktree, merge US-038 first"
summary: Compact state of the ADR-0021 knowledge framework after G1-G4, and the work packages another agent can pick up without this conversation.
---

# PLN-20261008-0923-us039-handoff-remaining-work — US-039 handoff

## Context

- Read first: `AGENTS.md`, `docs/knowledge/README.md`, `docs/INDEX.md`. Do not scan folders; the index lists every governed document.
- ADR-0021 (accepted 2026-10-06) set one contract for knowledge documents: YAML frontmatter, English, ids allocated by `python scripts/harness_cli.py doc new`, lint in pre-commit, `audit` and pytest. ADR-0022 sets WIP=1 per git worktree, keyed by the story's `branch`.
- Done and pushed on `feature/us039-knowledge-framework` (head `c7e7de2`, worktree `C:/src/news-scape-us039`).
  - Contract, scripts and templates; `AGENTS.md` in English; `CLAUDE.md` and `GEMINI.md` redirects.
  - ADR-0001 to ADR-0019 normalized, ADR-0015 added as rejected, plus ADR-0021 and ADR-0022.
  - 21 facts, 37 story files, 10 proposals renamed to PRP ids, 2 runs.
- Measured on 2026-10-08: `doc lint` 0 findings, 94 governed documents, 26 harness tests pass, `project/scripts/doc_lint.py` 0 violations.
- Still ungoverned (`docs/knowledge/legacy.txt`): 12 rules, 22 plans, ADR-0020, and the declared id `US-038`.
- Branches and worktrees:
  - `dev/us038` (`63f30d3`), worktree `C:/src/news-scraper-dev`, owned by the US-038 session. Merge target comes first.
  - `feature/us039-knowledge-framework`, worktree `C:/src/news-scape-us039`, forked from `dev/us038` at `2d47285`.
  - `fix/us040-code-first-guard` (`8442636`), worktree `C:/src/news-scape-us040`, forked from `dev/us038`. It has no `doc lint` yet because it predates US-039.
  - `main` is `aa49b5d`. Nothing of US-038, US-039 or US-040 is on `main`.
- Tooling facts that cost time:
  - `harness.db` is gitignored and per checkout. Pass `--db "C:/Users/anpt/OneDrive - fpts.com.vn/FRA_DataIngestion - news-scape/harness.db"` from other worktrees.
  - Never run the full `pytest tests/` in `project/`: `test_cli_entrypoints.py` writes to the operational DB. Run named test files only.
  - Frontmatter values containing `: ` must be quoted, or the YAML fails to parse (K01).
  - In Git Bash heredocs, avoid `\n` inside Python strings sent through `python -` with nested quotes; write files with the Write tool instead.
  - The pre-commit hook lives in the shared git dir `C:/gitdirs/news-scape.git/hooks/pre-commit` and skips the knowledge step on branches without `scripts/knowledge.py`.
  - `STOP-MIGRATION-US038.md` in the worktree root belongs to the US-038 session. Do not commit or delete it. The operator confirmed on 2026-10-06 that documentation work and temp-DB tests continue.

## Decisions

- ADR-0021: English harness documents, files are truth, `harness.db` is derived (`doc sync`), memory lives in `docs/knowledge/facts/`, accepted ADR bodies are frozen except the one-time normalization.
- ADR-0022: WIP=1 per worktree. A story with status `in_progress` MUST declare `branch`; lint reports K13 when two share a branch.
- `FACT-llm-runtimes-are-interchangeable`: DSH, agy, opencode, OpenRouter, Claude and Codex are equal runtime options. No document may call any of them dead, retired or replaced.
- Canonical story ids (operator delegated, 2026-10-06): US-033 capture reconcile, US-035 story clustering, US-036 Bronze wrong root, US-037 pipeline stabilization. Mislabelled commits are recorded in each story's Evidence.
- ADR-0004: item A2 is right, item A3 is stale. `verify_gold_quality.py --apply` ran on 2026-09-09 and its effect is in the operational DB (`FACT-adr-0004-d4-applied-to-operational-db`).
- US-040 fixed the `code_first` leak in eight live paths. Missing approvals from the past are recorded as "operator (date unrecorded)" and the schema accepts that.

## Design

- Types and paths come only from `docs/knowledge/schema.yaml`: adr, story, proposal, plan, fact, rule, run, runbook. Lint codes K00 to K13 are listed in `docs/knowledge/README.md`.
- To migrate a legacy file: add frontmatter, translate to English, keep numbers and decisions, mark rebuilt parts "(reconstructed from <source>)", cite only commits verified with `git cat-file -t`, then delete its line from `docs/knowledge/legacy.txt` and run `doc lint`.
- Work in the worktree that owns the branch. Commit per work package with Conventional Commits ending in `(US-NNN)`. Never run the DSH, daemon or wave commands for this work.
- Subagent pattern that worked: one agent per file group, read-only evidence gathering, no commits by the agent, the coordinator commits and trims `legacy.txt`.

## Roadmap

| Id | Work package | Lane | Size | Depends on | Acceptance |
|---|---|---|---|---|---|
| W1 | Merge order: US-038 into `main`, rebase US-039, then US-040. Conflicts expected in `docs/SESSION-LATEST.md` and `project/scripts/doc_lint.py` (one `DOC_GLOBS` line). Bring `scripts/knowledge.py` to the US-040 branch and lint its story | high-risk | S | US-038 merged | `doc lint` 0 findings on each branch after rebase |
| W2 | Migrate 12 rules to type rule. Add frontmatter, English, sections Scope, Rules, Verification, key `adr`. Allocate a number for `entity-system-invariants.md`. Set rule 05 (Gold) and the Gold parts of rule 06 samples to `retired` or rewrite them for the Article Lane. Keep rule 09 active "when DSH is chosen" | normal | M | none | Rules removed from `legacy.txt`; `AGENTS.md` still cites correct rule ids |
| W3 | Migrate 22 plans. Add frontmatter and a truthful status (7 old plans have none; `20260924-1627-codebase-audit...` and `20260924-research-council-execution` say "chờ duyệt", decide parked or dead from commits). Rename `plans/20260924-research-council-execution` to include HHMM or relax the id pattern in `schema.yaml` (decide and record). Phase files stay as is | normal | L | none | `plans/*/plan.md` all governed; `legacy.txt` has no plans |
| W4 | Collect tool-private plans into `plans/`: three files in `~/.claude/plans` (including `lovely-herding-moler.md`, cited by SESSION-LATEST), `.opencode/plans/US-NEMO01-...`, and the stale `.kilo/worktrees/granite-asphalt` copy | normal | S | W3 | No repo document cites `~/.claude/plans`; `.kilo` copy removed or ignored |
| W5 | ADR-0020: after the US-038 session finishes it, normalize to the contract (it lacks Alternatives and Rollback; `test_doc_lint` was red because of it). Create the story file for US-038 with `branch` and remove `id:US-038` from `legacy.txt` | high-risk | S | US-038 done | ADR-0020 governed; story US-038 has a file |
| W6 | Split `docs/SESSION-LATEST.md` by lane (`docs/sessions/<lane>.md`, each overwritten, one screen). Define the type in `schema.yaml` or document it as ungoverned. Split `docs/OPEN-ITEMS.md` into open and closed ledgers | normal | M | W1 | `SESSION-LATEST.md` is a pointer; no appended blocks |
| W7 | Translate the remaining Vietnamese harness documents to English: `HARNESS.md`, `FEATURE_INTAKE.md`, `CONTEXT_RULES.md`, `TRACE_SPEC.md`, `HARNESS_COMPONENTS.md`, `HARNESS_MATURITY.md`, `TOOL_REGISTRY.md`, `HARNESS_AUDIT.md`, `IMPROVEMENT_PROTOCOL.md`, `TEST_MATRIX.md`, `GLOSSARY.md`, `GIT_COMMIT_STANDARD.md`. Decide if they become governed types or stay reference pages | normal | L | none | No Vietnamese prose outside quotes in `docs/*.md` |
| W8 | Drift cleanup: `HARNESS.md` says H1 while `AGENTS.md` says H2-H5 (`HARNESS.md` lines 4, 11, 72; `HARNESS_BACKLOG.md` header); closure table uses an emoji against rule 06 (`HARNESS.md:42`, rule 04); ADR commit format differs between rule 04 and `GIT_COMMIT_STANDARD.md`; stale `project/data/monocle.db` paths in `OPEN-ITEMS.md`, `FEATURE_INTAKE.md`, rule 04; `HARNESS_BACKLOG.md` is a hand snapshot, regenerate or delete; two `project/docs/design/12-*` files; fold `project/docs/others/decisions.md` (TDR-001 to 006) into ADRs as superseded stubs | normal | M | W7 | Audit finds no live document naming a retired component or path |
| W9 | OKF and skills still describe the retired L1/Gold lane in about 21 files (`project/docs/design/15-...`, `project/docs/operations/daily-runbook-per-user.md`, `okf/catalog/playbooks/daily_agent_run.md`, `okf/catalog/tables/l1_tasks.md`, `okf/catalog/pipelines/article_lane.md` says "trên harness DSH"). Add a deprecation marker or rewrite for the Article Lane; add a lint rule that flags `l1_route` or `agent_export` in non-retired documents | normal | M | none | Lint rule green; each listed file marked or rewritten |
| W10 | Hand harness.db drift: story rows disagree with files (US-001 file said in_progress, DB blocked; US-034 DB blocked vs implemented). Run `doc sync` per checkout, then reconcile statuses with `story update`. `doc sync` only upserts stories that have files | tiny | S | W1 | `doc sync` reports no `db_only_stories` except retired ids |
| W11 | After merge only: reduce Claude `MEMORY.md` to pointers to `docs/knowledge/facts/`; check `~/.codex/memories` for facts missing from the repo | tiny | S | W1 | No fact exists only in a tool-private store |

## Verification

- `python scripts/harness_cli.py doc lint` returns `"count": 0` in every worktree.
- `cd project && python scripts/doc_lint.py` returns 0 violations.
- `python -m pytest tests/ -q` at the repository root passes (26 tests at last run). Inside `project/`, run named files only.
- `python scripts/harness_cli.py --db <path> audit` shows `knowledge_contract_findings: []` and no `wip_violation`.

## Out of Scope

- Pipeline, wave, daemon and DSH operations. No work package starts them.
- ADR-0020 content decisions (SharePoint publishing). That belongs to US-038.
- Rewriting accepted ADR bodies beyond the one-time normalization already done.

## Risks

- Operator decisions still open:
  - Done 2026-10-08 (operator approved): the live delivery root `C:/data/news-scape/users_output` was regenerated with the US-040 fix. 272 files were replaced and 656 moved to `C:/data/news-scape/archive/20261008-us040-code-first-delivery`. No legitimate article was lost.
  - Still open: the legacy copy `users/output` in the OneDrive repo folder (580 xlsx, last written 2026-10-05) still holds code-first articles. Decide whether users read that copy; if yes, apply the same staged files there.
  - Still open: three hand-made files (`2026-09-29-OpenRouter-AnPT.xlsx` and two `2026-09-15-FPA-AnPT.xlsx`) were not checked for code-first rows.
  - Confirm the ADR-0007 live-system acceptance proof (two real derive cycles with the dead-letter count on the radar). It was never checked.
- Known failing tests outside this work: `test_inherit.py::test_refresh_end_to_end_clusters_then_inherits` (fails on the base commit too) and four `test_periodic_reports` tests.
- Open items inherited from stories:
  - US-033: the criterion "missing under 2% per day" is red (radar reports 887 URLs waiting and four sources behind).
  - US-035: P3, P4, I3 and I5 are open.
  - US-037: R-06 and the rest of R-08 are open.
  - US-031: the P0 check on a real daemon wave is open.
  - ADR-0011: agy version pinning was never confirmed.
- Source facts that may be wrong: `FACT-*` files carry `verified` dates of 2026-10-06; two details diverge from the repo (`MAX_PARAGRAPH_CHARS` is 1600, not 1800).
- Parallel sessions can move `dev/us038` again. Run `git fetch --all` before rebasing and expect new conflicts in `SESSION-LATEST.md`.
