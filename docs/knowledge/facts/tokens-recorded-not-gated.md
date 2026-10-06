---
id: FACT-tokens-recorded-not-gated
type: fact
title: Tokens are recorded, never gated
status: active
created: 2026-09-23
updated: 2026-10-06
verified: 2026-09-23
lang: en
authors: [claude-opus-5-5]
adr: [ADR-0010]
evidence:
  - "path: AGENTS.md"
  - "path: project/scripts/token_ledger.py"
  - "commit: feb710c"
  - "operator: 2026-09-23 tokens are a record for the user to judge, never a limit or warning"
summary: Tokens are a recorded number for the operator to judge; no limit or warning threshold per article, batch or wave is allowed.
---

# FACT-tokens-recorded-not-gated — Tokens are recorded, never gated

## Fact

- Tokens MUST NOT act as a gate: no limit and no warning threshold per article, per batch or per wave.
- The ledger records tokens and USD only, so the operator can judge and estimate.
- Reports copy the numbers without calling them high or over, and never suggest fewer articles or smaller batches because of tokens.

## Why

- The operator said this directly on 2026-09-23 after an agent added `tokens_per_article_warn: 3500` and a "tokens per article over X, alert" table.
- The setting was removed in US-026 and recorded in ADR-0010 section 2.5 and AGENTS.md section 6B.

## How to Apply

- Post-checks and alerts use technical gates only: DB writable, ingest without error, wave coverage of at least 90%, `turns=1` and `reasoning=0`.
- Batch size comes from `--batch` only (see FACT-dsh-output-ceiling-256k).
