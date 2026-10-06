---
id: FACT-entity-recognition-recall-biased
type: fact
title: Entity recognition is recall-biased
status: active
created: 2026-09-18
updated: 2026-10-06
verified: 2026-09-18
lang: en
authors: [claude-opus-5-5]
adr: [ADR-0010]
evidence:
  - "path: plans/20260918-1651-article-lane-unified/plan.md"
  - "path: project/scripts/article_pack.py"
  - "operator: 2026-09-18 over-recognition is better than a missed entity (plan Q3)"
summary: The operator prefers over-recognition to missed entities, so watchlist tiering is recall-biased and every article gets full analysis; the tier decides order only.
---

# FACT-entity-recognition-recall-biased — Entity recognition is recall-biased

## Fact

- The operator rule is "nhận diện thừa còn hơn bỏ sót": raise true positives and cut false negatives.
- Tier 1 watchlist matching is recall-biased: tracked tickers, related sectors and urgent macro.
- Every article is processed in `full` mode; no `lite` mode exists (plan Q2, 2026-09-18).
- The tier decides processing order only, not depth.
- Measured on 2026-09-18 before the Article Lane: an L1 run over 25 headlines spent 845K tokens, a 12x waste factor over 82K unique content.
- 53% of that run was reading `entities.json`, which rule 08 forbids.
- The type drift `INDUSTRY_GICS1` against the id prefix `IND_GICS1:` was the root cause that pushed agents to probe the catalog.

## Why

- A missed entity removes an article from a user's delivery; an extra entity costs only a little review.
- The design plan was `plans/20260918-1651-article-lane-unified/plan.md`; parts of it, such as compact JSON and handoff thresholds, were later corrected.
- AGENTS.md section 6B restates the full-depth rule; the recall bias itself is recorded only in the plan, so the status stays active.

## How to Apply

- When tuning watchlist tiers or entity prompts, MUST NOT trade recall for precision without an operator decision.
- MUST NOT reintroduce a depth split by tier.
- Before blaming the model for catalog probing, check entity type and id prefix consistency in the catalog.
