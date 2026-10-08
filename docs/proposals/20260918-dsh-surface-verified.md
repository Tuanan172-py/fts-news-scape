---
id: PRP-20260918-dsh-surface-verified
type: proposal
title: DSH surface verified from source code
status: decided
lane: normal
created: 2026-09-18
updated: 2026-10-06
lang: en
authors: [An Pham Thanh (commit author)]
adr: [ADR-0009]
story: []
plan: []
related: [FACT-dsh-surface-verified, FACT-dsh-ptc-subagent-constraints, FACT-dsh-output-ceiling-256k, FACT-dsh-read-tool-line-limits, FACT-llm-runtimes-are-interchangeable]
evidence:
  - commit:3f9d59e
  - path:plans/20260918-1624-dsh-token-economy-workmethod/plan.md
  - path:docs/knowledge/facts/dsh-surface-verified.md
original: "commit:3f9d59e"
reconstructed: 2026-10-06
summary: Fact sheet verifying the DSH 0.1.5-rc.1 surface from source; it answered open questions U1-U6 for the ADR-0009 runtime and now lives on as FACT-dsh-surface-verified.
summary_vi: Bảng sự thật về bề mặt DSH 0.1.5-rc.1 đã kiểm bằng mã nguồn, trả lời U1-U6 cho ADR-0009 và được lưu thành FACT-dsh-surface-verified.
---

# PRP-20260918-dsh-surface-verified — DSH surface verified from source code

## Question

- What does the DSH runtime chosen in ADR-0009 actually do, verified line by line in its source, so presets and plans rest on facts instead of assumptions?
- The sheet is a static technical reference, not a plan. It was extracted from plan `20260918-1624-dsh-token-economy-workmethod` section 6, which was later marked superseded.

## Findings

- Source: `@deepseek-ai/*` 0.1.5-rc.1 under `%USERPROFILE%\.dsh\profiles\node_modules`, a junction to the npx tree. The header of the original called it DSH `0.1.5`. Labels: [V] verified in source, [U] not verified.
- The full verified table, with every `file:line` reference, now lives in FACT-dsh-surface-verified. PTC child limits live in FACT-dsh-ptc-subagent-constraints; the output ceiling in FACT-dsh-output-ceiling-256k.
- The four load-bearing facts named by the original:
  - `maxDepth: 0` forbids delegation entirely.
  - `run_code` is injected after `toolFilter`, so a PTC child never has zero tools.
  - The subagent row has no `mode` key, so a child always inherits the parent mode.
  - The tool-result pruner registers no listener, so nothing trims the transcript before the 80% compaction threshold.
- Key numbers: exactly 5 profiles; 9 subagent row keys; 4 `agentOptions` keys; `reasoningEffort` in `off`, `low`, `high`, `max` only; `maxTokens` default 256,000; `contextWindow` 1M.
- Compaction runs at 80% and retains 16%. Pruner threshold is 8,192 characters with head 4,096 and tail 1,024. Spill is 50,000 bytes. Parallel tool calls per step default to 10.
- Usage accounting: `inputTokens` is uncached input, `totalTokens` is per request, `reasoningTokens` is a subset of output, `cacheWriteTokens` is always 0, and DSH stores no cost. Six pitfalls reconciled exactly at `seq=283`.
- Child burn is absent from the parent `tokenUsage`. Measured: parent 158,277 uncached; children 158,898, 126,250 and 125,100.
- DSH has no token or cost cap per session or per day. Usage is read from session JSONL; the SQLite session store is mounted inert.

### Answered questions (replacing U1-U6 of plan revision 1)

| # | Question | Answer |
|---|---|---|
| U1 | Is `toolFilter.allow: []` valid? | Valid; it removes every inherited tool. Under `ptc`, `run_code` is added back, so zero tools needs `mode: native` (plan E15). |
| U2 | Can `reasoningEffort` be turned off? | Yes: `off` is one of the 4 values. |
| U3 | Default `maxTokens`? | 256,000, not 8K (plan E17). |
| U4 | Does a child's final message enter the parent context? | Under `ptc`: no, only logs and `return` or `print` values are model-facing. Under `native`: yes. This holds the architecture assumption if the conductor runs `ptc`. |
| U5 | Usage source? | JSONL under `~/.dsh/sessions/...`, field `assistant/message.usage`; the session SQLite is inert. |
| U6 | Can `headless` pick a preset? | No. Slim it with `--patch` or a profile overlay. |
| U7 | Real default GUI preset? | [U] `settings.yaml` says `ptc`, the web base says `standard`. To confirm with one command in Phase 00; conclusion E2 unchanged. |
| U8 | Does `--patch` or a headless overlay work end to end? | [U] Needs one real run in Phase 00. |

## Options

| Option | Benefit | Cost or risk |
|---|---|---|
| A. Keep the sheet as a durable reference outside `plans/` | Survives plan cleanup; the only baseline to re-check behaviour on a DSH upgrade | Needs re-verification at each upgrade |
| B. Leave the facts inside the plan | No extra file | Plans are cleaned periodically and this plan was superseded; the baseline would be lost |

## Recommendation

- Option A. On every DSH upgrade, reopen each `file:line` in the new version, update the fact first, then fix dependent presets and plans.
- Every reported token number MUST name its measure, because the GUI "Usage" figure includes cache reads.

## Outcome

- Decided: the sheet served as the verified basis for the ADR-0009 runtime and its Article Lane presets.
- 2026-10-06 (reconstructed under US-039): durable facts copied to FACT-dsh-surface-verified. DSH stays an interchangeable runtime option (FACT-llm-runtimes-are-interchangeable).
- Open items U7 and U8 remain unverified in this sheet.
