---
id: FACT-llm-owns-semantic-work
type: fact
title: LLM owns all semantic work
status: active
created: 2026-09-18
updated: 2026-10-06
verified: 2026-09-18
lang: en
authors: [claude-opus-5-5]
adr: [ADR-0010]
evidence:
  - "path: AGENTS.md"
  - "path: project/scripts/article_pack.py"
  - "operator: 2026-09-18 LLM content processing is the key of the project; code must not replace it"
summary: The LLM alone recognizes entities and summarizes; code only does mechanical work such as catalog lookup, packing, schema expansion and token measurement.
---

# FACT-llm-owns-semantic-work — LLM owns all semantic work

## Fact

- The operator calls LLM content processing the "key của dự án".
- Code MAY do mechanical support: catalog lookup after the LLM has named the surface form and group, packet packing, schema expansion and token measurement.
- Code MUST NOT replace the LLM for entity recognition or summarization: no code-first expansion and no regex emulation.

## Why

- The operator wants the LLM to recognize entities independently so it can "khai phá mở rộng" the otherwise fixed entity catalog.
- Code-first recognition removes that discovery ability.
- A cap that lets code decide what the LLM reads also breaks this boundary (see FACT-article-packets-carry-full-content).

## How to Apply

- When proposing token savings, offer only levers such as retrieval, expanders, caching and output compaction.
- Route every decision that carries meaning through the LLM.
- Deterministic matchers MAY check model output but MUST NOT count as analysis; `ANALYZED_L1` in `project/scripts/article_pack.py` excludes `l1_source = 'code_first'`.
