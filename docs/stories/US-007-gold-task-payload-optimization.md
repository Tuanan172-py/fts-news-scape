---
id: US-007
type: story
title: Gold task payload optimization, verbatim paragraph pruning and consolidated mini-batch handoff
status: retired
lane: normal
created: 2026-09-07
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
adr: [ADR-0010]
evidence: ["commit:193bfaf", "path:project/src/agent/pruner.py", "path:project/src/agent/batch_handoff.py", "test:project/tests/test_pruner_and_batch.py", "metric:6/6 tests passed, 263 suite passed", "metric:task packet size 182 KB to 6-8 KB"]
verify: "cd project; python -m pytest tests/test_pruner_and_batch.py"
original: "commit:193bfaf"
summary: Gold task packets shrank by 96 percent through link and image removal and verbatim paragraph pruning, and mini-batches cut subagent tool calls by 90 percent; retired by ADR-0010.
---

# US-007 — Gold task payload optimization, verbatim paragraph pruning and consolidated mini-batch handoff

## Contract

- Gold task packets MUST carry only the fields the analyst needs, so one packet no longer burns input tokens on DOM menus and image URLs.
- Pruned paragraphs MUST stay 100% verbatim so `citations` match `cleaned_text` character for character.
- Subagents MUST receive several articles per batch packet instead of one tool call pair per article.
- Gold tasks MUST carry the stock codes already found by L1.

## Acceptance Criteria

- [x] `src/agent/pruner.py` removes junk paragraphs and keeps verbatim paragraphs under a 4,000 character ceiling.
- [x] `build_gold_input()` in `src/agent/packet.py` drops `structure.links` and `images`; packet size falls from 182 KB to 6 to 8 KB.
- [x] `src/agent/batch_handoff.py` groups 5 to 10 articles into `batch_XX.task.json`, and `unpack_batch_output()` unpacks batch outputs for ingest.
- [x] `src/agent/runner.py` fills `input.l1_entities` from `l1_outputs`.
- [x] `--mini-batch` exists in `agent_export.py` and `run_agent_hierarchy.py`.
- [x] `tests/test_pruner_and_batch.py` passes (6 tests).

## Design Notes

- Problem: one task packet `04019f860...task.json` weighed 182 KB with thousands of menu links and image URLs. This drained input tokens, slowed I/O and degraded model attention.
- Problem: a batch of 50 articles needed 100 sequential tool calls.
- Problem: `cleaned_text` sometimes kept newsroom footer boilerplate, hotline details and related-article teasers. L1 results were not reused by Gold.
- Paragraph pruner: removes "related article" teasers, newsroom details, hotline, email, copyright and minor source lines.
- The pruner applies the inverted pyramid with a 4,000 character ceiling and keeps paragraphs verbatim.
- Zero-waste packet: `build_gold_input()` keeps only core fields, a 96% reduction.
- Mini-batch handoff: tool calls drop by 90%, from 20 calls per 10 articles to 2 calls.
- Also updated `.agents/skills/gold-financial-analyst/SKILL.md` with batch mode and fixed `_is_owner_alive()` in `src/db/store.py` for opaque identifiers.
- The original story file was lost on disk on 2026-09-07 (see US-008 data-loss incident). `pruner.py`, `batch_handoff.py` and the test were rebuilt from bytecode.
- Retired: ADR-0010 ended the two-tier L1/Gold lane. The Article Lane now sends full verbatim content; the pruner ceiling is disabled.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `cd project; python -m pytest tests/test_pruner_and_batch.py` | passed, 6/6 in 0.48s |
| Integration | full project suite | 263 passed, 0 failed |
| Platform | packet size benchmark | packet size down 96%; a 5-article batch packet is about 25 KB |

## Evidence

- `harness.db` story row US-007 (updated 2026-09-07) records unit, integration and e2e proof with the 6-test pytest run.
