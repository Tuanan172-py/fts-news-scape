---
id: US-049
type: story
title: Research codebase architecture and decide on module restructuring
status: in_progress
lane: high-risk
created: 2026-10-22
updated: 2026-10-22
lang: en
authors: [claude-opus-5-5]
branch: dev/us049-codebase-modularization
adr: [ADR-0027]
plan: []
related: [PRP-20261022-codebase-modularization, ADR-0010, ADR-0024]
evidence:
  - commit:ec4e7fe
  - path:docs/proposals/20261022-codebase-modularization.md
  - path:plans/20260924-1627-codebase-audit-cleanup-modularization/plan.md
verify: "python scripts/harness_cli.py doc lint"
summary: The operator gets a measured assessment of the codebase layout, its dead code and five gated restructuring stories, and decides before any operating code moves.
---

# US-049 — Research codebase architecture and decide on module restructuring

## Contract

- The operator MUST receive a measured map of the codebase (layering, import cycles, dead code reachable from no live entry point) and a ranked set of restructuring options with a recommendation.
- No operating code changes in this story. Implementation starts only after the operator decides the proposal; the hard gate holds until then (`status: blocked`).

## Acceptance Criteria

- [x] Import graph and reachability measured from the live entry points named in AGENTS.md §4 and `.agents/pipeline.yaml`.
- [x] The 2026-09-24 audit plan reconciled against the current tree: done and open items listed.
- [x] `PRP-20261022-codebase-modularization` lists options A-D with costs and one recommendation.
- [ ] Operator decision recorded in the proposal `Outcome`, followed by an ADR for the module-boundary rule and stories S1-S5.

## Design Notes

- Work runs in the worktree `C:/src/news-scraper-us049` (ADR-0022.D5, ADR-0024.D4) so the canonical tree that the daemon runs from stays untouched.
- Constraints: retired lane removal follows ADR-0010; CLI paths are a contract (proposal F7); tests MUST NOT write the operational DB (FACT-tests-must-not-write-operational-db).

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python scripts/harness_cli.py doc lint` | pass, 0 findings |
| Integration | baseline `pytest tests --ignore=tests/test_cli_entrypoints.py` in `project/` at `ec4e7fe` | 951 passed, 1 failed (`test_ops_council_fixes.py::test_b2_sensor_does_not_count_reserved_articles`, pre-existing, sensor returns 0 for a fixed 2026-10-01 fixture) |
| Platform | none, no runtime change | n/a |

## Evidence

- Proposal: `docs/proposals/20261022-codebase-modularization.md`.
- Blocked reason: high-risk lane; waiting for the operator to choose an option.
