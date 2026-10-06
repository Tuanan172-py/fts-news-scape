---
id: FACT-llm-runtimes-are-interchangeable
type: fact
title: LLM runtimes are interchangeable options
status: active
created: 2026-10-06
updated: 2026-10-06
verified: 2026-10-06
lang: en
authors: [claude-opus-5-5]
adr: [ADR-0009, ADR-0011, ADR-0017]
evidence:
  - "operator: 2026-10-06 DSH is treated like OpenRouter, agy, Claude and Codex; never retire DSH"
  - path:docs/decisions/0017-hop-dong-dau-ra-article-lane-thong-nhat-moi-provider.md
summary: DSH, agy, opencode, OpenRouter, Claude and Codex are equal, optional LLM runtimes for executing Article Lane tasks; none is retired and none is privileged except agy as the conformance benchmark.
---

# FACT-llm-runtimes-are-interchangeable — LLM runtimes are interchangeable options

## Fact

- The runtime layer chooses one LLM runtime per execution task (Article Lane wave or batch). The options are DSH, agy, opencode, OpenRouter API, Claude and Codex.
- Every option is treated the same way: one output contract and one validator (ADR-0017). A runtime enters the lane after it passes the golden set.
- No runtime is retired. The operator ruled on 2026-10-06: "tuyệt đối ko có ý niệm loại bỏ DSH".
- agy keeps its role as the conformance benchmark (ADR-0017). That role does not make it the only runner.

## Why

- A session note of 2026-10-06 said DSH was no longer used, and the ADR normalization first read that as DSH being dead. The operator corrected it the same day.
- Retiring a runtime in documents would push agents to delete presets, rules (rule 09) or the conductor program that remain valid options.

## How to Apply

- MUST NOT describe any runtime as dead, retired or replaced. Say which runtime a wave used, not which runtimes exist.
- Runtime-specific rules (for example `.agents/rules/09-dsh-preflight-gate.md`) apply whenever that runtime is chosen.
- Adding a runtime means passing the ADR-0017 golden set, not writing a new ADR that replaces another runtime.
