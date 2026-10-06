---
id: PRP-20260917-dsh-harness-mapping
type: proposal
title: DSH harness framework for the News-Scape agent network
status: decided
lane: high-risk
created: 2026-09-17
updated: 2026-10-06
lang: en
authors: [An Pham Thanh (commit author)]
adr: [ADR-0009]
story: []
plan: []
related: [ADR-0010, ADR-0017, PRP-20260918-dsh-surface-verified, FACT-dsh-surface-verified, FACT-llm-runtimes-are-interchangeable]
evidence:
  - commit:0f1a65c
  - path:plans/20260917-1538-dsh-harness-integration/plan.md
  - metric:163 L1 batches waiting for a manual subagent, 90 articles not routed to L1, 0 Gold waiting (pipeline_radar.py status, 2026-09-17)
  - path:.agents/registry.yaml
  - path:.agents/pipeline.yaml
original: "commit:0f1a65c"
reconstructed: 2026-10-06
summary: Should DSH become the LLM orchestration runtime generated from registry.yaml and pipeline.yaml? Recommended in-process subagents (Option A) with a PTC conductor; the operator approved D1-D6 as ADR-0009.
summary_vi: Đề xuất dùng DSH làm runtime điều phối LLM sinh từ registry và pipeline, chọn subagent in-process với Conductor PTC; người vận hành duyệt D1-D6 thành ADR-0009.
---

# PRP-20260917-dsh-harness-mapping — DSH harness framework for the News-Scape agent network

## Question

- Should DeepSeek Harness (DSH) supply the missing LLM orchestration runtime, as an execution layer generated from `.agents/registry.yaml`, `.agents/pipeline.yaml` and `harness.db`, without moving the source of truth?
- Lane: high-risk (touches harness core and the automation substrate). The proposal changed no code, touched no `monocle.db` and opened no story.

## Findings

### Gap at proposal time

- Three data spines were complete: Spine 1 `registry.yaml`, Spine 2 `pipeline.yaml` (DAG with `needs`, `gate`, `wave`), Spine 3 `harness.db.agent_metrics`.
- `OPEN-ITEMS C2`: no module in the repository called an LLM API, so queues only grew.
- `OPEN-ITEMS A0-6`: `agy.exe --dangerously-skip-permissions` lived outside the repository, unpinned and not reproducible.
- Measured with `pipeline_radar.py status` on 2026-09-17: 163 L1 batches waiting for a manual subagent, 90 articles not routed to L1, 0 Gold articles waiting.
- G3: orchestration lived in SKILL prose and depended on human memory. G4: KPIs were declared as `metric_hook` but not fed after ingest.
- `dsh-skill-filesystem` already loaded `.agents/skills` at rank 200, with project root the nearest `.git`. All 16 project skills appeared in the session catalog.

### Mapping of News-Scape concepts to DSH primitives

| News-Scape concept | DSH primitive | Enforcement |
|---|---|---|
| operator (0 token, Python) | Global tool registered by plugin `@news-scape/dsh-harness`, or `pwsh` ad hoc | `ToolRuntime.register` with canonical JSON `output.schema` |
| cognitive | One `dsh-tool-subagent` instance (`provider: spawn`) per agent | `toolFilter: {allow: [read, write]}`, `persona`, `agentOptions.model`, `maxDepth: 0` |
| conductor | Session mounting preset `news-scape-conductor` | Preset scope, PTC, skill, goal |
| `registry.yaml` | Source for a generator `scripts/build_dsh_harness.py` | Generator fails on an invalid registry |
| `pipeline.yaml` | Tool `ns_pipeline_next` and a gate-before-advance guard | Deterministic plugin logic |
| `agent_metrics` | `tools/result` waterfall and tool `ns_metric` | Hook writes `harness.db` after each ingest |
| wave `{batch, concurrency}` | `maxParallelSubCalls` (PTC) and `backgroundMode` | `run_code` pool scheduler |
| WIP=1 | `tools/pre-execute` guard reading `harness.db` | Refuses when a story is `in_progress` |
| Tier-3, ADR, human approval | `dsh-plan-mode` and `ask_user_question` | Hard gate before mutation |
| Zero-Probe (rule 08) | `ns_radar` as the only reconnaissance tool | `toolFilter` and skill policy |

### Key design facts

- In DSH a child joins the parent composition; presets are chosen per session, not per subagent. The per-agent 2-I/O boundary therefore lives in the subagent instance configuration.
- `toolFilter.allow: [read, write]` removes every other global tool from the prompt and refuses its execution. This matches `tools_allowed: [view_file, write_to_file]`.
- Proposed architecture has three planes: a data plane (unchanged source of truth), a host plane (operator tools, subagent rows, hooks, skills) and an agent plane (conductor, native and tier3 presets).
- The conductor sketch used `mode: ptc` and `maxParallelSubCalls: 3`, matching registry L1 concurrency 3. The Gold wave was 2 in parallel at 5 articles per batch; L1 batches held 25 titles.
- Proposed hooks: WIP guard, gate-before-advance guard blocking `gold_export` until `l1_ingest` is green, metric-after-ingest waterfall, and a tier3 write guard limited to `data/proposals/*`.
- Roadmap H1 to H4: H1 read-only radar and next-stage tools; H2 cognitive L1 with 75 articles passing DoD and `tokens_per_item` compared with a budget of 450; H3 Gold plus gate; H4 governance.
- Risks: a runtime outside the repository (the A0-6 lesson), two orchestrators running at once, children inheriting PTC, open model routes for `pro` and `flash-lite`, and 24 uncommitted files in the working tree.
- Anti-scope: no move of the source of truth to DSH, no rewrite of Python operators as plugins, no Tier-3 automation without an ADR, no deletion of rules or skills.
- The DSH line-level facts behind this design were verified the next day in PRP-20260918-dsh-surface-verified.

## Options

| Option | Benefit | Cost or risk |
|---|---|---|
| A. In-process subagent per cognitive agent, PTC conductor | One process and one preset; events land in the same session log; per-child `toolFilter`, `persona` and model | Children inherit the parent PTC mode |
| B. One top-level session per cognitive agent with its own preset | Stronger isolation, own model route, native mode | Many processes, heavier orchestration, launched through the CLI |
| C. Keep `agy.exe` | No new runtime | Unpinned, outside the repository, skips permissions (A0-6) |
| D. Write a custom LLM runner | Full control | New code to build and maintain |

## Recommendation

- Option A for the whole daily delivery path; reserve Option B for Tier-3 agents (entity-curator) and long-running specialists (harness-auditor) where isolation is mandatory.
- DSH MUST NOT replace the source of truth; it is an execution layer generated from it. Pin the DSH version.
- The draft ADR proposed: "Use DSH (agent presets, in-process subagent, PTC, hooks) as the orchestration runtime", keeping `agy` as an alternative.

## Outcome

- 2026-09-17: the operator approved D1-D6 in plan `20260917-1538-dsh-harness-integration`, recorded as ADR-0009.
- ADR-0009 chose Option A, kept `agy` as a non-default runner, and restricted models to DeepSeek Flash.
- Later direction (reconstructed 2026-10-06): the lane design was replaced by the Article Lane (ADR-0010), and ADR-0017 put every provider under one output contract.
- DSH remains one interchangeable runtime option, never retired (FACT-llm-runtimes-are-interchangeable).
