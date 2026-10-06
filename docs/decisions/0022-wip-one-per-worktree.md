---
id: ADR-0022
type: adr
title: WIP limit of one story per worktree
status: accepted
lane: high-risk
created: 2026-10-06
updated: 2026-10-06
lang: en
authors: [claude-opus-5-5]
approvers: [operator 2026-10-06]
story: [US-039]
amends: [ADR-0001]
related: [ADR-0021]
evidence:
  - "operator: 2026-10-06 WIP=1 per worktree; agents on different stories and worktrees are equal and have full authority there"
  - path:AGENTS.md
  - path:docs/HARNESS.md
  - path:.agents/rules/04-harness-durable-invariants.md
  - metric:US-038 and US-039 in_progress at once on two worktrees, query matrix 2026-10-06
summary: WIP=1 applies per git worktree, keyed by branch; agents on different worktrees work in parallel with equal authority, and lint blocks two in_progress stories on one branch.
summary_vi: WIP=1 áp dụng cho từng worktree theo nhánh; agent trên các worktree khác nhau làm song song, ngang quyền.
---

# ADR-0022 — WIP limit of one story per worktree

## Context

- The harness defined WIP=1 globally: at most one story `in_progress` in the whole project (AGENTS.md section 1, `docs/HARNESS.md` section 3, rule 04, rule 07, glossary, audit check 2).
- The operator now runs several agents in parallel, each in its own git worktree: US-038 in `C:/src/news-scraper-dev` and US-039 in `C:/src/news-scape-us039` on 2026-10-06.
- Under the global rule, the second session either violated WIP=1 or had to park a story that another agent was actively working on. Neither reflects how the operator works.
- The global rule also had no mechanical enforcement (backlog item 2 in `docs/HARNESS_BACKLOG.md`); the audit counted `in_progress` rows in `harness.db` without knowing which session owned them.
- Git already guarantees that one branch is checked out in at most one worktree, so a branch is a reliable key for a work lane.

## Decision

- D1. WIP=1 applies per git worktree. In one worktree at most one story is `in_progress`. Different worktrees run in parallel.
- D2. Agents on different worktrees are equal. Each has full authority over its own worktree, branch and story; none parks or edits another worktree's story without the operator.
- D3. A story in status `in_progress` MUST declare its `branch` in frontmatter. The branch identifies the worktree.
- D4. `harness_cli.py doc lint` reports K13 when two stories with status `in_progress` declare the same branch. The audit check `wip_violation` uses the same rule.
- D5. Work that touches files another worktree is changing SHOULD start its own worktree and branch, and the later merge rebases onto the earlier one, as US-039 did with US-038.
- D6. Interruptions inside one worktree keep the old discipline: park the current story (`blocked` or `deferred`, with a reason) before starting another one there.

## Alternatives

| Option | Why rejected |
|---|---|
| Keep WIP=1 global | Forces parallel sessions to violate the rule or park each other's work; rejected by the operator on 2026-10-06. |
| Drop the WIP limit | Loses interrupt discipline inside one session, the original reason for the rule in ADR-0001. |
| Key WIP by agent or model name | Agents are anonymous and interchangeable (ADR-0021); one model can run several sessions. Branches are unique per worktree by git design. |
| Key WIP by a `worktree` path | Paths differ between machines; the branch name travels with the repository. |

## Consequences

Gains:

- Parallel agents no longer produce false WIP violations, and the audit penalty reflects real conflicts inside one worktree.
- WIP becomes mechanically checked for the first time, through frontmatter and lint.

Costs accepted:

- Two worktrees can still change the same file. D5 and the merge order handle this; it is a merge cost, not a WIP rule.
- Stories that exist only in `harness.db` carry no branch. The audit lists them as unattributed without a penalty until they get files.

## Rollback

- Revert this ADR's commit and the K13 check in `scripts/knowledge.py`; the `branch` key stays optional and harmless.
- AGENTS.md section 1 returns to the global wording. Only the operator may order the rollback.

## Follow-up

- [x] Add `branch` to the story schema, required when status is `in_progress`.
- [x] Add K13 to `doc lint` and switch the audit `wip_violation` check to per-branch counting.
- [x] Point AGENTS.md section 1, glossary, `docs/HARNESS.md`, rule 04, rule 07 and the audit table to this ADR.
