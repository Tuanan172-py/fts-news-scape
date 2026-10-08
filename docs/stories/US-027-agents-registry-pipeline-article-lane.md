---
id: US-027
type: story
title: AGENTS.md, registry and pipeline aligned to Article Lane
status: implemented
lane: high-risk
created: 2026-09-23
updated: 2026-10-06
lang: en
authors: [unknown]
adr: [ADR-0010]
plan: []
evidence: [commit:bb47e44, path:docs/decisions/0010-ngung-lane-l1-gold-article-lane-duy-nhat.md, path:.agents/registry.yaml, path:.agents/pipeline.yaml, metric:517 tests passed]
verify: "python -m pytest tests/ -q"
reconstructed: 2026-10-06
summary: ADR-0010 was accepted, and AGENTS.md, the agent registry and the pipeline DAG were rewritten so the Article Lane is the only operating path and legacy lane agents are retired.
---

# US-027 — AGENTS.md, registry and pipeline aligned to Article Lane

## Contract

- ADR-0010 is accepted, with operator approval on 2026-09-23 (reconstructed from the harness.db row).
- AGENTS.md MUST NOT describe the L1/Gold lane as an operating path.
- `.agents/registry.yaml` MUST mark legacy lane agents `retired`; `.agents/pipeline.yaml` MUST contain no legacy lane stage.
- DB write access is required only at `--finish`; wave preparation is not blocked.

## Acceptance Criteria

- [x] AGENTS.md no longer describes the L1/Gold lane as an operating path.
- [x] Registry: `l1-router`, `gold-exporter`, `l1-entity-matcher` and `gold-financial-analyst` are `retired`.
- [x] Pipeline: six legacy stages removed; no dangling agent or `needs` reference.
- [x] Harness audit reports no new error, and pytest passes 100%.

## Design Notes

- AGENTS.md sections 2, 3, 6 and 8 were rewritten; the subscriber gate, pruning, missed-only L1, mini-batch and `invoke_subagent` text were removed.
- The user list now points to the manifest instead of a hard-coded user name.
- The US-025 advice to add DSH writable roots was wrong; DSH has no such setting (trace 76).
- One test was added proving wave preparation runs without DB write access.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python -m pytest tests/ -q` | 517 passed |
| Integration | YAML check of `pipeline.yaml` | no dangling agent or `needs` |
| Platform | radar status on 2026-09-23 | recommends only `article_run` commands |

## Evidence

- Commit bb47e44 (2026-09-24), the ADR-0010 governance change, tagged US-027.
- harness.db story row US-027 and trace 76, outcome `completed`.
