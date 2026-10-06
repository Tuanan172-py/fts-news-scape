---
id: FACT-dsh-ptc-subagent-constraints
type: fact
title: DSH PTC subagent constraints
status: active
created: 2026-09-18
updated: 2026-10-06
verified: 2026-09-18
lang: en
authors: [claude-opus-5-5]
adr: []
evidence:
  - "path: docs/proposals/20260918-dsh-surface-verified.md"
  - "path: .agents/dsh/RUNBOOK-article-lane.md"
summary: In DSH 0.1.5 a PTC parent can only spawn PTC children that always keep run_code, and maxDepth 0 forbids any delegation.
---

# FACT-dsh-ptc-subagent-constraints — DSH PTC subagent constraints

## Fact

Verified on 2026-09-18 in the DSH 0.1.5 source under `~/.dsh/profiles/node_modules/@deepseek-ai`:

- The `dsh-tool-subagent` row has exactly 9 keys and no `mode` key (`dsh-tool-subagent/lib/index.js:252-270`).
- A child inherits the parent presentation mode through the layer chain (`dsh-tools/lib/index.js:2668`, `modeFor`). A conductor in `ptc` makes every child `ptc`.
- `run_code` is injected after the `toolFilter` layer (`dsh-tools:2874`), and `restrict()` throws when a row names `run_code` (`:2800`).
- So `toolFilter.allow: []` under `ptc` leaves exactly one tool, `run_code`, never zero tools. The SDK inside `run_code` is then empty (`:2923`), so the child cannot read files.
- `maxDepth: 0` forbids delegation entirely: `childDepth = depth(parent)+1`, so the first child is 1 > 0 and raises `SubagentDepthError` (`dsh-subagent/lib/types/child-agent.js:32-41`).
- `dsh-compaction-tool-result-pruner` only exports a class and registers no listener. It runs only inside a compaction pass, which starts automatically at 80% of the window.
- A PTC child with `allow: []` still receives the `tools:ptc-only` section of about 40 tokens. It also receives the `tools:sdk` section of 1,802 characters, about 600 tokens, ending in an empty `interface ToolArgsMap {}`.

## Why

- A truly zero-tool native worker needs an out-of-process runner (`headless` or `sdk-minimal`).
- Decision of 2026-09-18: use the in-process PTC child, not SDK or headless.
- Accepted costs: the conductor keeps `mode: ptc`, AGENTS.md stays in the child prefix, and about 640 tokens of empty SDK text sit in the cached static prefix.
- The retired `agent_l1` and `agent_gold` tools declared `maxDepth: 0`, so they never spawned a child.

## How to Apply

- The worker persona MUST explicitly cancel the prompt text that invites the model to write `run_code` programs.
- Watch the `turns == 1` metric to confirm the worker made exactly one step.
- Re-check every file:line reference above when upgrading DSH.
