---
id: US-026
type: story
title: Token as record only and legacy lane cleanup
status: implemented
lane: normal
created: 2026-09-23
updated: 2026-10-06
lang: en
authors: [unknown]
adr: [ADR-0010]
plan: []
evidence: [commit:feb710c, path:project/scripts/token_ledger.py, path:project/src/morninger.py, path:.agents/dsh/presets/news-scape-conductor/agent.cordis.yml, wave:W365, metric:516 tests passed]
verify: "python -m pytest tests/ -q"
reconstructed: 2026-10-06
summary: Token counts became a record with no per-article threshold, the preset lost agent_l1 and agent_gold, finish ingests only its own wave files, and morninger stopped scheduling l1_route.
---

# US-026 — Token as record only and legacy lane cleanup

## Contract

- Token usage MUST be recorded only; no per-article, per-batch or per-wave threshold or warning may exist (reconstructed from harness.db evidence and trace 75).
- The DSH preset MUST NOT carry `agent_l1` or `agent_gold`, and morninger MUST NOT register `l1_route`.
- `--finish` MUST ingest only files of its own wave; the article selector MUST NOT count code-first output as analyzed.

## Acceptance Criteria

- [x] No per-article token threshold remains.
- [x] The preset no longer has `agent_l1` or `agent_gold`.
- [x] `--finish` ingests only the files of its wave.
- [x] Morninger does not register `l1_route`.
- [x] `article_pack` does not exclude articles that only have `code_first` output.
- [x] pytest passes 100%.

## Design Notes

- The harness.db `product_contract` is empty; the contract above is reconstructed from the acceptance criteria and evidence.
- `tokens_per_article_warn` and its warning were removed from `token_ledger` and `token_pricing.yaml`.
- `ANALYZED_L1` dropped `code_first`, so 2,915 articles from 2026-09-10 to 2026-09-17 returned to the queue.
- 38 legacy items moved to `data/archive/legacy-lane-20260923` with a MANIFEST, not deleted.
- Trace 75 notes morninger had run since 2026-09-17 with old code and needed an operator restart.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python -m pytest tests/ -q` | 516 passed |
| Integration | preset YAML parse and `build_article_prefix --check` | pass, one subagent row left |
| Platform | `--finish` on wave W365 | done 365, failed 0 (before: failed 123); L1 365 of 365 |

## Evidence

- Commit feb710c (2026-09-24), the token-as-record and `l1_route` removal change, tagged US-026.
- harness.db story row US-026 and trace 75, outcome `completed`.
