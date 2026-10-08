---
id: US-014
type: story
title: Context budget counts orchestrator reads only, not delegated subagent reads
status: implemented
lane: tiny
created: 2026-09-17
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
adr: []
related: [US-011]
evidence: ["commit:0f1a65c", "path:docs/CONTEXT_RULES.md", "path:docs/TRACE_SPEC.md", "metric:traces 46, 47 and 48 scored score_context 1.0"]
verify: "git diff --stat docs/CONTEXT_RULES.md docs/TRACE_SPEC.md"
original: "commit:0f1a65c"
summary: The context budget rule stops penalizing delegation to subagents and counts only files read into the orchestrating agent's own context window.
---

# US-014 — Context budget counts orchestrator reads only, not delegated subagent reads

## Contract

- The context budget rule MUST NOT penalize delegating exploration to subagents.
- It MUST serve its declared purpose: controlling the context window of the orchestrating agent.
- The story closes backlog #6.

## Acceptance Criteria

- [x] `docs/CONTEXT_RULES.md` §1 gains a block on the scope of the file-count ceiling.
- [x] `docs/TRACE_SPEC.md` §3 gains the matching bullet for the `score_context` formula.
- [x] Backlog #6 is closed with an `Outcome`.

## Design Notes

- `docs/CONTEXT_RULES.md` §1 set a ceiling of 10 to 15 files for lane `normal`, with the stated purpose of avoiding context window overflow.
- The `score_context` formula (`docs/TRACE_SPEC.md` §3) counted every `files_read` entry in the trace, including files read by Explore subagents.
- Those files never occupy the orchestrator's context window. They stay in the subagent's own context and return only as a condensed report.
- The rule therefore penalized the very behavior it encouraged, creating a reverse incentive to read everything inline for a better score.
- Proof: the US-011 trace (#45) was complete and honest but scored `score_context = 0.6` because it listed the files of two Explore subagents.
- No mechanical test exists for a pure policy document change; the proof is the document diff.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `git diff --stat docs/CONTEXT_RULES.md docs/TRACE_SPEC.md` | both files changed |
| Integration | next three traces scored under the new rule | #46, #47, #48 all `score_context = 1.0` |
| Platform | none | not applicable |

## Evidence

- The effect was visible in the same session: traces #46 (US-012), #47 (US-013) and #48 (US-014) listed `files_read` under the new rule and scored `score_context = 1.0`.
- Their exploration volume was larger than US-011 (two Explore subagents plus several direct read rounds). The score now reflects context window occupancy instead of penalizing delegation.
- Backlog #6 closed. Backlog #7 (broken `project/.venv`) stayed open; deletion was only proposed and awaited confirmation as a destructive action.
- Trace #48: `score_trace = 1.0`, `score_context = 1.0`. Outcome: completed.
- Commit 52307cd also carries the tag US-014 but belongs to a different change (three-tier ticker catalog); the id was reused.
