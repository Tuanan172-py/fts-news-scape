---
id: ADR-0006
type: adr
title: Agent network with registry, pipeline DAG and per-agent KPI ledger
status: accepted
lane: high-risk
created: 2026-09-15
updated: 2026-10-06
lang: en
authors: [An Pham Thanh (commit author)]
approvers: ["operator (date unrecorded)"]
story: [US-010]
evidence:
  - commit:e765737
  - path:.agents/registry.yaml
  - path:.agents/pipeline.yaml
  - path:.agents/AGENT_NETWORK_DESIGN.md
  - path:.agents/rules/07-agent-registry-governance.md
  - path:scripts/schema/002-agent-metrics.sql
  - path:scripts/harness_cli.py
  - test:tests/test_harness_cli.py (7 passed at commit e765737)
  - metric:harness.db schema_version 2 after init, applied 001-init.sql and 002-agent-metrics.sql (2026-09-15)
  - metric:2 of 5 "agents" in the swarm diagram were real LLM subagents, grep audit 2026-09-15
original: "commit:e765737"
reconstructed: 2026-10-06
summary: Three-class agent taxonomy (operator, cognitive, conductor), a machine-readable registry and pipeline DAG as source of truth, an agent_metrics KPI ledger in harness.db, and six draft cognitive agents.
summary_vi: Chuẩn hoá ba lớp tác nhân, lập registry và pipeline DAG làm nguồn chân lý, thêm sổ KPI agent_metrics trong harness.db và sáu cognitive agent ở trạng thái draft.
---

# ADR-0006 — Agent network with registry, pipeline DAG and per-agent KPI ledger

## Context

- G1, mixed terminology. The "Multi-Agent Swarm" diagram named five "agents". A grep audit showed only two were real LLM subagents: `l1-entity-matcher` and `gold-financial-analyst`.
- The other four (Query Radar, Token Auditor, DoD Gatekeeper, Delivery) were deterministic zero-token scripts. Nobody could reason about where a real LLM agent should be added.
- G2 and G5, no machine-readable source of truth. I/O boundaries, model, token budget and DoD contract of each agent were scattered across prose in `skills/` and `rules/`.
- The payload invariants were duplicated between rule 05 and `AGENTS.md` §6, which risked drift.
- G3, implicit orchestration. Stage order, dependencies, DoD gates and the wave policy against HTTP 429 lived in runbook prose. They depended on operator memory and could not be audited.
- G4, no per-agent data for self-improvement. `harness_cli propose` read only a manual friction backlog. No ledger measured `dod_pass_rate`, `tokens` or `fp_flags` per agent to detect regressions early.

The design survey behind this ADR is `.agents/AGENT_NETWORK_DESIGN.md`, written on 2026-09-15 as a draft for approval. It states four axioms: deterministic work stays in zero-token scripts, an agent exists only as a declared entry, orchestration is data, and nothing is added that cannot be measured.

## Decision

- D1. Three-class taxonomy. Every actor is one of: **operator** (deterministic zero-token script), **cognitive** (paid LLM subagent) or **conductor** (orchestrator that reads the manifest). Documents and the registry MUST state `class`. An operator MUST NOT be called an "agent".
- D2. Spine 1, agent registry. `.agents/registry.yaml` is the single source of truth for every actor. Each entry uses one schema: `id`, `class`, `status`, `model`, `io_boundary`, `tools_allowed`, `dod_contract`, `cost_budget`, `kpis`, `owner_rules`. Rules and skills MUST reference the registry instead of repeating it.
- D3. Spine 2, pipeline DAG manifest. The five-phase prose process becomes a declared DAG in `.agents/pipeline.yaml`: `stages[]` with `needs`, `gate`, `wave`, `optional`. `pipeline_radar` reads the manifest to derive the next stage and the wave policy instead of hardcoding them.
- D3a. The manifest records the `invariants` the conductor MUST obey: WIP=1, Controlled Wave, No Script Emulation, Gate-before-advance, Metric hook.
- D4. Spine 3, per-agent KPI ledger. `harness.db` moves to schema v2 with table `agent_metrics` (migration `002-agent-metrics.sql`). The CLI gains `metric` (write) and `query agent-metrics` (rollup).
- D4a. `init_db` applies every `NNN-*.sql` migration in order, idempotent through `IF NOT EXISTS`.
- D4b. `propose` reads per-agent trends. It flags an agent with `dod_pass_rate` below 95% or `fp_flags` above 0, and raises the lane to `high-risk` when a threshold is crossed.
- D5. Six specialist cognitive agents are created with `status: draft`: `story-dedup-clusterer`, `materiality-triage`, `entity-curator`, `adversarial-dod-verifier`, `daily-brief-synthesizer`, `harness-auditor`.
- D5a. Each draft agent has one `SKILL.md`, one registry entry and one pipeline stage. `entity-curator` is tier high-risk and needs its own ADR before activation, because it touches the catalog Data Contract.

## Alternatives

The original ADR lists no alternatives. The rows below are reconstructed from the gap table and anti-scope of `.agents/AGENT_NETWORK_DESIGN.md` at commit e765737.

| Option | Why rejected |
|---|---|
| Keep describing agents in skill and rule prose only | Gaps G1 to G5: adding an agent stays ad hoc, invariants drift between rule 05 and `AGENTS.md` §6, and nothing can be audited (reconstructed from the design gap table). |
| Keep stage order and wave policy in runbooks | Orchestration depends on operator memory and `pipeline_radar` keeps hardcoded stage logic (reconstructed from gap G3). |
| Put `agent_metrics` in the business database `monocle.db` | The design anti-scope keeps `harness.db` separate from `monocle.db`; KPIs belong to the harness (reconstructed from design §7). |
| Automate `invoke_subagent` in code now | The design anti-scope defers this until the platform exposes a stable API; only the orchestration around it is declared (reconstructed from design §7). |

## Consequences

Gains:

- Adding an agent becomes a controlled declarative step: registry entry, pipeline stage, story and KPI.
- Orchestration becomes auditable, the self-improvement loop gets per-agent numbers, and duplicated invariants are removed.

Costs accepted:

- `harness.db` moves to schema v2. The original text calls this irreversible once applied, but idempotent and backward compatible; old tables stay intact.
- The documentation surface under `.agents/` grows.

Verification at acceptance (commit e765737):

- `harness_cli.py init` returned `schema_version: 2` with `[001-init.sql, 002-agent-metrics.sql]` applied.
- `harness_cli.py query contract` listed capabilities `metric` and `agent-metrics`.
- `harness_cli.py propose` flagged a test agent with `dod_pass_rate=80%` and `fp_flags=1` and raised its lane to `high-risk`.
- `pytest tests/test_harness_cli.py` passed 7 tests, including the ledger and the auto-flag case.

### Current status (2026-10-06)

- D1 in force. `.agents/registry.yaml` still declares `class` for every entry.
- D2 in force, amended by ADR-0010: `l1-router`, `gold-exporter`, `l1-entity-matcher` and `gold-financial-analyst` are now `status: retired`.
- D3 in force, amended by ADR-0010: stages `l1_route`, `l1_match`, `gold_export` and `gold_analyze` were removed from the pipeline.
- D4 in force, amended by ADR-0014: runtime traces go to `ops_spans` and KPIs are derived from them at wave close. ADR-0014 measured `agent_metrics` at zero rows.
- D5 partly dead. `materiality-triage` was retired on 2026-09-24 and `story-dedup-clusterer` on 2026-10-02 (ADR-0016); the other four remain `draft` in the registry.

## Rollback

- The original ADR names no rollback procedure. The declarative files (`registry.yaml`, `pipeline.yaml`, rule 07, six skills) can be removed with a `git revert` of commit e765737 (reconstructed from the commit file list).
- The schema v2 migration stays in `harness.db`; the original text accepts that it is irreversible but leaves old tables intact.
- Under the high-risk lane (`AGENTS.md` §0) a rollback needs operator approval.

## Follow-up

- [x] Registry, pipeline manifest, rule 07 and six draft skills committed in e765737.
- [x] Migration `002-agent-metrics.sql` applied to the live `harness.db`.
- [ ] Write `agent_metrics` rows from real waves; ADR-0014 owns the ingestion path from `ops_spans`.
- [ ] Decide the fate of the four remaining draft agents (`entity-curator`, `adversarial-dod-verifier`, `daily-brief-synthesizer`, `harness-auditor`).
