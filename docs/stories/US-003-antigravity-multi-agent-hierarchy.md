---
id: US-003
type: story
title: Multi-agent hierarchy integration on Antigravity 2.0 (all-flash)
status: retired
lane: normal
created: 2026-08-24
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
adr: [ADR-0010]
evidence: ["commit:3a0c527", "path:project/scripts/run_agent_hierarchy.py", "path:project/docs/design/15-antigravity-multi-agent-orchestration.md", "metric:241 tests passed"]
verify: "historical: no verify command recorded"
original: "commit:3a0c527"
reconstructed: 2026-10-06
summary: Antigravity 2.0 all-flash agent hierarchy with rules, skills and an end-to-end runner replaced static Gold stubs; the L1/Gold lane it served was retired by ADR-0010.
---

# US-003 — Multi-agent hierarchy integration on Antigravity 2.0 (all-flash)

## Contract

- Gold extraction MUST use real model analysis instead of static stubs (`agent_process_packets.py`, `agent_stub.py`) with hardcoded `materiality_score = 0.6` and `sentiment = neutral`.
- The hierarchy uses the `flash` model for every subagent: `L1-Entity-Matcher`, `Gold-Financial-Analyst`, `DoD-Auto-Healer`.
- One runner MUST chain export, agent execution, DoD ingest and user compilation, which previously needed separate manual CLI calls.

## Acceptance Criteria

- [x] AC-1 (rules and guardrails): `.agents/rules/01-subagent-guardrails.md` enforces the I/O boundary: read only task packets, write only outputs, strict grounding, no DB or code modification.
- [x] AC-2 (financial domain rules): `.agents/rules/02-financial-domain-rules.md` defines guidelines for `materiality_score` (0.1 to 1.0) and `sentiment`.
- [x] AC-3 (skills): `.agents/skills/l1-entity-matcher/SKILL.md` and `.agents/skills/gold-financial-analyst/SKILL.md` exist for progressive disclosure.
- [x] AC-4 (hierarchy runner): `project/scripts/run_agent_hierarchy.py` bridges export, status and dispatch, DoD ingest, self-healing summary and user output delivery.
- [x] AC-5 (architecture doc): `project/docs/design/15-antigravity-multi-agent-orchestration.md` documents the Antigravity 2.0 orchestration protocol.
- [x] AC-6 (proof): all existing 241 unit and integration tests still pass.

## Design Notes

- Implementation log: created the two rules, the two skills, `run_agent_hierarchy.py` and design doc 15.
- Reconstructed: the original file had no lane, status or intake date; lane `normal` and date 2026-08-24 come from commit 3a0c527. No `harness.db` row exists.
- Retired: ADR-0010 ended the two-tier L1/Gold lane. `run_agent_hierarchy.py` and the `gold-financial-analyst` skill no longer run; `l1-entity-matcher` survives as recognition knowledge of `article-processor`.
- `materiality_score` was later dropped from every tier, so AC-2 no longer describes current behavior.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | full test suite at the time | 241 passed |
| Integration | none recorded | not run |
| Platform | none recorded | not run |

## Evidence

- Commit 3a0c527 (2026-08-24): "feat: complete multi-agent hierarchy, entity system, durable harness & concurrency safe I/O".
