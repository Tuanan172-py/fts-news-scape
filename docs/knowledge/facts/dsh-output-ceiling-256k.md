---
id: FACT-dsh-output-ceiling-256k
type: fact
title: DSH output ceiling is 256K tokens
status: active
created: 2026-09-21
updated: 2026-10-06
verified: 2026-09-21
lang: en
authors: [claude-opus-5-5]
adr: []
evidence:
  - "path: docs/proposals/20260918-dsh-surface-verified.md"
  - "path: project/scripts/article_run.py"
summary: The real DSH output ceiling is 256,000 tokens per request; the old 40,000 limit was set by the project itself, so a 100-article wave runs in one call.
---

# FACT-dsh-output-ceiling-256k — DSH output ceiling is 256K tokens

## Fact

- The default DSH `maxTokens` is 256,000 tokens per request (`DEFAULT_MAX_TOKENS = 256e3`). A child inherits it from the parent when its row sets none.
- Source: `docs/proposals/20260918-dsh-surface-verified.md` sections 6.1 and 6.2, read from the DSH source.
- DSH has no token or cost ceiling per session or per day.
- The 40,000 figure once called a "provider ceiling" was a value the project itself set on the `tool-subagent-article` row.
- That value truncated the 100-article batches of W1 and W2 and forced 10 calls of 10 articles. It was removed on 2026-09-21; the three subagent rows are now identical.
- A 100-article wave uses about 154K input tokens (25% of the window, full content) and about 90K output tokens. That leaves almost three times headroom under 256K.

## Why

- The constraint did not exist. The refuting evidence sat in the project's own documents for three days.
- Before calling a number a constraint, check whether the project set it.

## How to Apply

- `--batch` is the only batching gate.
- When a batch returns missing articles, run `article_run.py --wave <code> --repair` to repack exactly the missing part. Repair after the fact; do not pre-split.
