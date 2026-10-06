---
id: FACT-article-packets-carry-full-content
type: fact
title: Article packets carry full content
status: active
created: 2026-09-21
updated: 2026-10-06
verified: 2026-10-06
lang: en
authors: [claude-opus-5-5]
adr: []
evidence:
  - "path: project/src/agent/distill.py"
summary: DEFAULT_MAX_TOKENS_PER_ARTICLE is 0 (no cut) since 2026-09-21 because the old 900-token cap dropped 46% of content before the model read it.
---

# FACT-article-packets-carry-full-content — Article packets carry full content

## Fact

- `DEFAULT_MAX_TOKENS_PER_ARTICLE` in `project/src/agent/distill.py` is 0, meaning no cut, since 2026-09-21.
- The previous value of 900 dropped 46% of content before the model read it.
- Measured on 600 articles: 1,542 tokens after mechanical filtering became 838 tokens actually sent, and 81% of articles were cut.
- With full content a 100-article wave uses 154K input tokens, 25% of the window.
- Uncached input tokens cost 50 times less than output tokens.
- The remaining mechanical filters remove noise only: boilerplate 2.8% and lines under 40 characters 8.6%.

## Why

- The cap existed to save input tokens, but the measurements refuted that reason.
- Letting code decide what the LLM reads violates FACT-llm-owns-semantic-work.

## How to Apply

- Keep the default at 0.
- `--max-tokens-per-article` still exists for manual use only.
- Line-length safety comes from paragraph splitting, see FACT-dsh-read-tool-line-limits.
