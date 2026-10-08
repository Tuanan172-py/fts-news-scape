---
id: US-010
type: story
title: Agent network registry, pipeline DAG and KPI ledger
status: implemented
lane: high-risk
created: 2026-09-15
updated: 2026-10-06
lang: en
authors: [unknown]
adr: [ADR-0006]
plan: []
evidence: [commit:e765737, path:.agents/registry.yaml, path:.agents/pipeline.yaml, path:scripts/schema/002-agent-metrics.sql, test:tests/test_harness_cli.py]
verify: "C:/venvs/news-scape/Scripts/python.exe -m pytest tests/test_harness_cli.py -q"
reconstructed: 2026-10-06
summary: The agent network is declared in three spine files, six specialist agents exist as drafts, and harness.db gains an agent_metrics ledger that the propose command reads.
---

# US-010 — Agent network registry, pipeline DAG and KPI ledger

## Contract

- The repository MUST declare the agent network in machine-readable spines: `.agents/registry.yaml` for agents and `.agents/pipeline.yaml` for the DAG (reconstructed from the harness.db row and trace 35).
- harness.db MUST store per-agent KPIs in an `agent_metrics` table added by migration `002-agent-metrics.sql`.
- `harness_cli.py propose` MUST read `agent_metrics` when it generates improvement proposals.
- Six specialist agents exist as draft skills, governed by rule 07.

## Acceptance Criteria

- [x] Harness tests pass.
- [x] Migration `002-agent-metrics.sql` is applied.
- [x] `propose` reads `agent_metrics`.

## Design Notes

- Decision recorded in ADR-0006; growth rules in `.agents/rules/07-agent-registry-governance.md`.
- Trace 35 lists the deliverables: `registry.yaml`, `pipeline.yaml`, the migration, `harness_cli` commands `metric`, `agent-metrics` and `propose`, six `SKILL.md` files and an AGENTS.md link.
- Commit d119a8f mentions "US-009/010/011" in its subject; that numbering predates harness.db and does not refer to this story.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python -m pytest tests/test_harness_cli.py -q` | 7 passed (harness.db evidence) |
| Integration | none recorded | not run |
| Platform | none recorded | not run |

## Evidence

- Commit e765737 (2026-09-15) adds `registry.yaml`, `pipeline.yaml`, rule 07, ADR-0006, migration 002 and `harness_cli.py` changes.
- harness.db story row US-010 and trace 35, outcome `completed`.
