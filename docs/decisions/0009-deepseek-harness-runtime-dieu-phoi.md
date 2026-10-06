---
id: ADR-0009
type: adr
title: DeepSeek Harness as orchestration runtime for the agent network
status: accepted
lane: high-risk
created: 2026-09-17
updated: 2026-10-06
lang: en
authors: [An Pham Thanh (commit author)]
approvers: [operator 2026-09-17]
story: [US-020, US-021, US-022, US-023]
evidence:
  - commit:42bc104
  - commit:c6c2a56
  - commit:3f9d59e
  - commit:bb47e44
  - commit:dd1e709
  - commit:2497137
  - path:plans/20260917-1538-dsh-harness-integration/plan.md
  - path:docs/proposals/dsh-harness-mapping-2026-09-17.md
  - path:docs/proposals/dsh-surface-verified-2026-09-18.md
  - path:plans/20260918-1651-article-lane-unified/plan.md
  - metric:163 L1 batches waiting for a manual subagent, 90 articles not yet routed to L1, proposal 2026-09-17
  - metric:845K-token trace in the 2026-09-17 session run through the generic subagent, article-lane plan 2026-09-18
  - operator:plan decisions D1-D6 approved 2026-09-17
  - operator:DSH no longer used as runner; runners are agy and opencode (SESSION-LATEST 2026-10-06)
original: "commit:3f9d59e"
reconstructed: 2026-10-06
summary: DSH became the orchestration runtime with cognitive agents as in-process subagents, DeepSeek Flash only, ADR-0008 gate with L1 60,000 and Gold 40,000 token caps, PTC conductor, agy kept as non-default option.
summary_vi: Chọn DSH làm runtime điều phối với subagent in-process, chỉ dùng DeepSeek Flash, cổng ADR 0008 kèm trần token, Conductor chạy PTC và giữ agy làm phương án phụ.
---

# ADR-0009 — DeepSeek Harness as orchestration runtime for the agent network

## Context

- The three data spines of ADR-0006 (registry, pipeline, metrics) were mature, but no LLM runtime existed.
- `OPEN-ITEMS C2` confirmed that no module in the repository called an LLM API.
- `OPEN-ITEMS A0-6` recorded that `agy.exe --dangerously-skip-permissions` lived outside the repository, with no pinned version, and was not reproducible.
- US-016 to US-019 had fixed the data integrity defects and built the demand-driven pull model (Q5).
- ADR-0008 required a human in the loop and a token cap before any token spend.
- Measured backlog at proposal time: 163 L1 batches waiting for a manual subagent, 90 articles not routed to L1, 0 Gold articles waiting (reconstructed from `docs/proposals/dsh-harness-mapping-2026-09-17.md` §0).
- The proposal mapped DSH features to the gap: in-process subagents with per-child tool control, agent presets and PTC mode (reconstructed from the same proposal).
- It also listed automatic skill loading from `.agents/skills` and a hook pipeline for WIP=1 and gate checks (reconstructed from the same proposal).

## Decision

Sub-decision numbers follow the plan ids the operator approved on 2026-09-17 (plan D1, D2, D4, D6), so ADR-0017's citation of "ADR 0009 D6" resolves to the model decision. D3, D5 and D7 hold the remaining sections. Plan D5 (read-only H1 approval on the operational database) lives only in the plan. Original section numbers are given in brackets.

- D1 (§2.2, Option A). Each cognitive agent is an in-process subagent: one `dsh-tool-subagent` instance with `provider: spawn`, its own `persona`, and `toolFilter` and `maxDepth` set per role. Children inherit the parent composition. Per-agent boundaries live in the instance configuration, not in separate presets.
- D2 (§2.7). `agy` stays an option, not the default. The default path uses DSH. `auto_pilot.py` and `agy` are kept as a runnable alternative runner, not run now, with quality verification deferred. Every runner MUST pass ADR-0008.
- D3 (§2.1). DSH is the orchestration runtime: agent presets, in-process subagents, PTC and the hook pipeline. `registry.yaml`, `pipeline.yaml`, `harness.db` and `.agents/skills` stay the source of truth. The DSH composition is GENERATED from them, by a generator in H3.
- D4 (§2.6). Packaging roadmap: H1 and H2 are wired with `cordis.patch.yml`; H3 and H4 are packaged as a local bundle `@news-scape/dsh-harness`.
- D5 (§2.4). The ADR-0008 gate is enforced. Before every token spend the conductor MUST show batches, articles, model, token estimate and effort, and ask by default. Caps are 60,000 tokens per L1 run and 40,000 per Gold run. H3 turns the gate into a hard-enforced tool `ns_activate`.
- D6 (§2.3). Only the DeepSeek Flash 4.1 family is used. Every agent route is `deepseek-official/deepseek-flash` (`DeepSeek-V41-Flash`). `deepseek-v4-pro` is forbidden because of token cost. The four `pro` agents in the registry move to flash; `entity-curator` keeps its Tier-3 gate.
- D7 (§2.5). The conductor runs in `mode: ptc` with a native fallback. The wave valve is held by the orchestration script, not by harness configuration.

### Amendment history

**2026-09-18, D1: `maxDepth: 0` corrected to `maxDepth: 1`.** Anchor: `plans/20260918-1651-article-lane-unified/plan.md` §3.1 and §4.2. Content preserved:

- The original set `maxDepth: 0` intending "block recursion". Reading DSH 0.1.5 source showed this was wrong.
- `dsh-subagent/lib/types/child-agent.js:32-41` computes `childDepth = delegationDepthOf(parent) + 1`. The first child is already at depth 1, and `1 > 0` makes every call throw `SubagentDepthError`.
- The `dsh-tool-subagent` README line 53 states: "`0` forbids delegation".
- Observed effect: `agent_l1` and `agent_gold` never spawned since the preset was created. This was one of two reasons the 2026-09-17 session used the generic `subagent`; the other was a wrong preset.
- The generic `subagent` has no `toolFilter`, so the whole 2-I/O boundary was lost. That led directly to the 845K-token trace.
- Fix: `maxDepth: 1` allows exactly one child level and still blocks grandchildren, which meets the original intent.
- Addendum, `toolFilter` cannot enforce what the original described. `dsh-tools/lib/index.js:2874` inserts `run_code` into the visible tool set after `toolFilter` runs, and line 2800 throws if `restrict()` tries to name `run_code`.
- Under `mode: ptc`, a child with `allow: []` still has `run_code`; its inner SDK is empty, so it cannot touch files. The boundary holds, but the check is "sdkSchemas empty" and "turns == 1", not "0 tools".
- Addendum, a child's `mode` cannot be set. The subagent row schema has exactly 9 keys (`dsh-tool-subagent/lib/index.js:252-270`) and no `mode`. The child inherits the parent mode, so the conductor MUST stay in `ptc`.

**2026-09-18, D7: `maxParallelSubCalls: 3` and the native fallback removed.** Anchor: `plans/20260918-1651-article-lane-unified/plan.md` §4.2 R1 and §16. Content preserved:

- `maxParallelSubCalls: 3` was never configured anywhere in the repository or the DSH profile; the effective value was always the default 10.
- It belongs to the `@deepseek-ai/dsh-tools` row at host plane (`dsh-tools/lib/index.js:2575`), not to the subagent row, so a preset cannot set it.
- The original reason for the wave valve was HTTP 429. That reason no longer holds: DeepSeek has no TPM or RPM limit, only a concurrency limit of 2,500 for `deepseek-flash`, three orders of magnitude above this system's need.
- Replacement: the wave valve lives in `project/scripts/article_run.py` (`--concurrency`, default 3), in project code that can be read and tested. Host configuration is not touched.
- Native fallback removed. The original said "fall back to native if flash quality under PTC is insufficient". Under `native`, sub-call results flow straight into the conductor context, about 30,000 tokens per batch. `ptc` is a structural requirement, not a performance option.

## Alternatives

| Option | Why rejected |
|---|---|
| Keep `agy` as the default | Not reproducible, no human gate, no 2-I/O enforcement. |
| One top-level preset per agent (Option B) | Many processes and heavy orchestration; DSH already lets children inherit the composition. |
| Write an in-repository LLM runner | Duplicates DSH; no ready-made presets, skills or hooks. |
| Use `deepseek-v4-pro` for QA and brief agents | Exceeds the token budget (D6). |

## Consequences

Gains:

- Controlled cognitive automation; 2-I/O, wave, gate, WIP and metrics enforced by machine; project skills load automatically; the unreproducible external runner is replaced.

Costs and governance:

- Dependency on a DSH runtime outside the repository, which MUST be version-pinned.
- QA and brief quality on flash is unverified until H4. Children inherit PTC. A registry amendment is required.

Acceptance tiers defined by the original ADR:

| Tier | Condition |
|---|---|
| Unit | Generator output is byte-identical; `ns_activate` does not spawn without confirmation |
| Integration | A child sees only `read` and `write`; WIP and gate guards block correctly |
| Platform | H1: database hash unchanged. H2: one L1 wave with DoD at least 95% plus metric. H4: the full 2026-09-17 workflow on the operational database, 0 models other than flash |

### Current status (2026-10-06)

- D1 amended by ADR-0010: rows `agent_l1` and `agent_gold` were removed from the preset; `article-processor` is the only cognitive worker.
- D2 reversed by ADR-0011: `agy` became a headless Article Lane runner next to DSH, no longer only an option.
- D3 dead in practice. On 2026-10-06 the operator stated that DSH is no longer used as runner; the runners are agy and opencode (commit 2497137, `docs/SESSION-LATEST.md`).
- D4 dead. H3 and H4 were deferred in the plan status table and no `@news-scape/dsh-harness` bundle was found.
- D5 dead. ADR-0008 is superseded; ADR-0010.D5 removes every token cap and ADR-0014 forbids rebuilding the approval gate.
- D6 overridden by ADR-0017: providers other than `deepseek-flash` are allowed once they pass the golden set.
- D7 as amended remains the design of the DSH conductor program; it is inactive while DSH is not used as runner.

## Rollback

- The original ADR names no rollback procedure. The plan anti-scope kept `auto_pilot.py` and `agy` runnable and not deleted, which preserved a path back to the pre-DSH runner (reconstructed from `plans/20260917-1538-dsh-harness-integration/plan.md` §11).
- ADR-0010 records how to restore the removed preset rows from git if needed.
- Under the high-risk lane (`AGENTS.md` §0) a rollback needs operator approval.

## Follow-up

- [x] H1 preset `news-scape-conductor` and skill, H2 `agent_l1` and `agent_gold` rows, registry moved to flash (plan status table, 2026-09-17).
- [ ] H3 bundle, `ns_activate` and generator: deferred in the plan; superseded in practice by ADR-0010 and ADR-0011.
- [ ] Write a new ADR that formally retires DSH as runner, citing the operator statement of 2026-10-06.
