---
id: FACT-dsh-surface-verified
type: fact
title: DSH surface verified facts
status: active
created: 2026-10-06
updated: 2026-10-06
verified: 2026-09-18
lang: en
authors: [claude-opus-5-5]
adr: [ADR-0009]
proposal: [PRP-20260918-dsh-surface-verified]
related: [FACT-dsh-output-ceiling-256k, FACT-dsh-ptc-subagent-constraints, FACT-dsh-read-tool-line-limits, FACT-llm-runtimes-are-interchangeable]
evidence:
  - path:docs/proposals/20260918-dsh-surface-verified.md
  - path:plans/20260918-1624-dsh-token-economy-workmethod/plan.md
  - commit:3f9d59e
summary: DSH 0.1.5-rc.1 source facts on profiles, subagent rows, reasoning effort, compaction, spill, step structure and usage accounting, verified on 2026-09-18 for re-checking at every DSH upgrade.
---

# FACT-dsh-surface-verified — DSH surface verified facts

## Fact

Verified on 2026-09-18 in the `@deepseek-ai/*` 0.1.5-rc.1 source. `%USERPROFILE%\.dsh\profiles\node_modules` is a junction to the npx tree, so both paths hold one source tree. Limits of subagents under PTC live in FACT-dsh-ptc-subagent-constraints. The 256,000 output ceiling lives in FACT-dsh-output-ceiling-256k.

### Profiles and boot

- Exactly 5 profiles ship: `acp`, `web`, `headless`, `sdk`, `sdk-minimal`. `tui`, `rescue` and `desktop` do not exist; `desktop` is hard-blocked (`dsh-app-boot/lib/index.js:327-355`).
- A missing `$DSH_HOME/profiles/<name>/package.json` whose name is a template is created automatically, without error (`dsh-app-boot/lib/index.js:886-892`).
- `headless` runs one task per process. Stdout holds only the final message, reasoning goes to stderr, exit is 0 or 1 (`dsh-headless/lib/index.js:26,163-167`).
- `headless` has no preset, no `--json` and no usage output, and MUST start through the `dsh` launcher (`dsh-headless/README.md:12,123,126`).
- `--patch <file>` and `$DSH_HOME/profiles/<name>/cordis.patch.yml` apply after every bundle layer. This is the only way to slim a `headless` or `sdk` composition (`dsh/lib/profile-boot-*.js:305-310`).

### Subagent rows

- `provider` on a subagent row is the backend (spawn, fork, acp, codex, claude-code), not the LLM provider (`dsh-tool-subagent/README.md:83`).
- `agentOptions` has 4 keys: `provider`, `model`, `reasoningEffort`, `maxTokens` (`dsh-tool-subagent/lib/index.js:258-263`).
- `reasoningEffort` accepts only `off`, `low`, `high`, `max`. No `medium`, `minimal` or `none` exists (`dsh-llm-deepseek/lib/index.js:26-28`).
- `toolFilter` accepts only `{allow?, deny?}`. `{}` throws at mount; an unknown tool name throws at the first delegation, not at mount (`dsh-tool-subagent:265-268,370`; `dsh-tools:2795-2804`).
- A child joins the parent preset (`composeFrom`); no key turns that off (`dsh-subagent/lib/index.js:543`).
- Only the child's final message crosses back. Transcript and tool I/O stay in the child. The final message has no cap; only the 120-character summary line and 4,096-byte diagnostics are capped (`dsh-subagent:185,217,661,2475`).
- Under `ptc` a child's final message does not enter the parent context; only logs and `return` or `print` values are model-facing. Under `native` it does.

### Prompt and context

- Child prompt section order is fixed and the tool list is lexicographic. Runtime and time context sit at the tail, so the prefix is stable and the tail changes every step (`dsh-system-prompt:96,112,133`; `dsh-time-context:231`).
- AGENTS.md is reloaded for every agent, children included, deduplicated by digest. Setting `agent-instructions.config.maxBytes <= 0` removes it (`dsh-agent-instructions:668,1270`).
- Compaction runs automatically at 80% of the window and retains 16% (`thresholdRatio 0.8`, `retainRatio 0.16`, `auto true`). It rewrites the surface, so the cache is lost from that point (`dsh-compaction-basic:15,17,76,111`).
- The tool-result pruner (`thresholdChars 8192`, head 4096, tail 1024) registers no listener and runs only inside compaction (`dsh-compaction-tool-result-pruner:11,137`).
- Spill threshold is 50,000 bytes (`maxInlineBytes`) with a head and tail preview plus a path. `read` and nested calls are exempt (`dsh-spill-policy:74,104,157`; `dsh-base/cordis.patch.yml:386`).
- Text tool results are not stored by reference. They stay verbatim and are resent every step until spill, prune or compaction (`dsh-session:1204,1269`).

### Steps and parallelism

- One request per step. All tool calls in one assistant message run inside that step, up to 10 in parallel, then one new request follows (`dsh-agent-loop:1116,1118,1226`).
- `maxParallelSubCalls` defaults to 10 and belongs to the `dsh-tools` row, not the subagent row (`dsh-tools:2575`).

### Usage accounting

- `assistant/message.data.usage` holds `{inputTokens, outputTokens, totalTokens, cacheReadTokens, reasoningTokens}`. `inputTokens = prompt_tokens - cacheRead`, so it is the uncached part; `prompt_cache_hit_tokens` is not stored (`dsh-llm-deepseek:1146-1166`).
- `totalTokens` is per request, not cumulative. `reasoningTokens` is a subset of `outputTokens`. `cacheWriteTokens` is always 0 with the DeepSeek adapter.
- DSH stores no price or cost anywhere, so `billed_usd` MUST be computed outside DSH.
- `surfaceTokens = systemTokens + messageTokens` without `toolsTokens`. `pressureTokens = input + cacheRead + cacheWrite` of the latest sample, without output. These six pitfalls reconciled exactly at `seq=283`.
- The GUI "Usage" figure is `uncachedInput + cacheRead + cacheWrite + output`, so it counts cache reads. The per-turn pill labels uncached input as "Input". No `/usage` or `dsh usage` command exists (`dsh-client-ui-chat/lib/client.js:3942,4016`).
- Child burn does not appear in the parent `tokenUsage`. Measured: parent 158,277 uncached; three children 158,898, 126,250 and 125,100. Full wave cost needs `subagentCatalog` plus each child's projcache.
- DSH has no token or cost cap per session or per day. The only numeric limits: `maxTokens` 256,000 per request, `contextWindow` 1M, compaction 0.8x, pruner 8,192 characters, spill 50,000 bytes (`dsh-llm:132,174`).
- Out-of-process usage is read from JSONL under `~/.dsh/sessions/<workspace-key>/<uuid>/`. `dsh-session-query-sqlite` is mounted inert (`path: ':memory:'`, `openAt: never`) (`dsh-base/cordis.patch.yml:110-113,129-133`).
- `dsh-token-meter` exposes only an in-process projection; external scripts parse JSONL themselves (`dsh-token-meter/lib/index.js:609-615`).
- A Claude Code and Codex hook bridge package exists, but no composition mounts it; only native extension points work.

### Presets

- Under the `standard` preset PTC is off (no code runtime mounted); `tool-presentation` defaults to `native`.
- `.dsh/settings.yaml` declares `ptc`, while the web app registers `standard` as base. Neither value is `news-scape-conductor` (`settings.yaml:11-12`; `dsh-web-app/cordis.patch.yml:480-484`).

## Why

- These facts were extracted from plan `20260918-1624-dsh-token-economy-workmethod` section 6, which was later marked superseded. They are the only baseline for checking DSH behaviour after an upgrade.
- Wrong assumptions here cost tokens: a reported "Usage" number that silently includes cache reads, or a wave cost that omits child burn.
- DSH remains an interchangeable runtime option (FACT-llm-runtimes-are-interchangeable); these facts stay valid while that option is used.

## How to Apply

- On every DSH upgrade, reopen each `file:line` above in the new version. Update this fact first, then fix dependent presets or plans.
- Every reported token number MUST state its measure (uncached input, cache read, or GUI usage).
- Compute wave cost from session JSONL, summing the parent and every child session.
- Two items were unverified on 2026-09-18 and stay open: the real default GUI preset (`ptc` versus `standard`) and an end-to-end `headless` run with `--patch`.
