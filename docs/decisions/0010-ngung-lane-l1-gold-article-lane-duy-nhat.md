---
id: ADR-0010
type: adr
title: Retire the two-tier L1/Gold lane; Article Lane is the only processing path
status: accepted
lane: high-risk
created: 2026-09-23
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
approvers: [operator 2026-09-23]
story: [US-026, US-027]
supersedes: [ADR-0003, ADR-0004, ADR-0008]
amends: [ADR-0005, ADR-0006, ADR-0009]
evidence:
  - commit:bb47e44
  - commit:feb710c
  - commit:77e166f
  - commit:ad148c4
  - commit:2497137
  - path:plans/20260918-1651-article-lane-unified/plan.md
  - path:.agents/registry.yaml
  - path:.agents/pipeline.yaml
  - metric:2,915 articles dated 2026-09-10 to 2026-09-17 never analysed because code-first rows counted as analysed, review 2026-09-23
  - metric:4 W365 articles rejected with reason no l1_task, review 2026-09-23
  - metric:85 stale L1 files re-ingested per wave, failed rows inflated to 123, review 2026-09-23
  - metric:wave W365 on 2026-09-21, 365 articles, 5 users delivered
  - operator:approved 2026-09-23 with three directives (remove agent_l1/agent_gold rows, update AGENTS.md, clean old-lane noise)
original: "commit:bb47e44"
reconstructed: 2026-10-06
summary: Article Lane becomes the single processing path; the L1/Gold lane, its preset rows, morninger job, pipeline stages and registry agents are retired, code-first rows never count as analysed, tokens are recorded only.
summary_vi: Ngừng hẳn lane L1/Gold hai tầng, Article Lane là đường xử lý duy nhất, bản code-first không tính là đã phân tích, token chỉ ghi nhận.
---

# ADR-0010 — Retire the two-tier L1/Gold lane; Article Lane is the only processing path

## Context

- Article Lane has run since 2026-09-18. One agent (`article-processor`, tool `agent_article`) processes a whole article in one step per batch, covering entity recognition and content analysis.
- The old lane was kept as a fallback, on the condition "clean up after one clean operating cycle". Wave W365 on 2026-09-21 (365 articles, 5 users delivered) was that cycle.
- A review on 2026-09-23 found that the old lane was not dormant but causing harm:

| Old-lane remnant | Measured harm |
|---|---|
| Radar still recommended `l1_entity_matcher`, `requeue`, `l1_route` | Conductor sessions obeying the radar-first rule were led into a dead lane |
| The `morninger` job ran `l1_route` plus `l1_ingest --code-first` every 15 minutes | It wrote lookup rows into `l1_outputs`. The Article Lane selector treated them as analysed, so 2,915 articles dated 2026-09-10 to 2026-09-17 were never analysed |
| `L1Runner` required an old-lane `l1_tasks` row | 4 W365 articles were rejected with reason `no l1_task` although the model answered correctly |
| Stale files in the shared output folder; `--finish` scanned the whole folder | 85 old L1 files failing schema were re-ingested every wave, inflating `failed` rows to 123 |
| `agent_l1` and `agent_gold` rows in the preset | They never spawned (ADR-0009 amendment) but still appeared in the conductor tool list |

The unified plan scheduled archive and deprecation of the old path as step 6, after one clean day of the new lane (reconstructed from `plans/20260918-1651-article-lane-unified/plan.md` §11). The W365 handoff left 441 old-lane L1 batches unprocessed (reconstructed from commit ad148c4).

## Decision

- D1. Article Lane is the only processing path. No fallback to the two-tier L1/Gold lane remains. Skill `l1-entity-matcher` stays because it is the recognition knowledge of `article-processor`. Skill `gold-financial-analyst` remains reference material only.
- D2. Removed from operation: the `agent_l1` and `agent_gold` preset rows; the `l1_route` job of `morninger`; pipeline stages `l1_route`, `l1_match`, `gold_export`, `gold_analyze`. Stages `l1_ingest` and `gold_ingest` merge into `article_expand`.
- D2 (cont.). Registry agents `l1-router`, `gold-exporter`, `l1-entity-matcher` and `gold-financial-analyst` move to `status: retired`.
- D3. Kept with a new role: `l1_ingest.py` and `agent_ingest.py` stay as DoD acceptance gates. Only `article_run.py --finish` MAY call them, and only with the files of that exact wave.
- D4. A code-first row is not an analysis. Every "analysed" count and the article selector MUST ignore `l1_source = 'code_first'`.
- D5. Tokens are a recorded figure, not a gate. No token ceiling or warning level exists per article, batch or wave. The ledger records tokens for the user to judge. The token-ceiling part of ADR-0008 lapses.
- D6. The real gate of a wave is technical: the DB is writable (checked before spending tokens), ingest has no errors, and wave coverage is at least 90% on both layers.

## Alternatives

| Option | Why rejected |
|---|---|
| Keep the old lane "frozen but callable" as a fallback, as plan §11.1 proposed | The review measured active harm while frozen: 2,915 stranded articles, 4 false rejections, 123 inflated failures. A dormant path still feeds radar and selectors. |
| Keep code-first rows counted as analysed | Their presence in `l1_outputs` hid 2,915 articles from the selector. Deterministic lookup is not semantic analysis (reconstructed from commit ad148c4, `docs/CODE-FIRST-LANDSCAPE.md`). |
| Keep the token ceilings of ADR-0008 | The operator ordered tokens to be recorded only; ceilings and warning levels were removed from pricing config and the preset (reconstructed from commit feb710c). |
| Delete stale old-lane files outright | Destroys the audit trail. Files move to an archive with a manifest so the move can be undone. |

## Consequences

- Stale files move (not deleted) to `project/data/archive/legacy-lane-20260923/`, with `MANIFEST.json` for undo.
- Old `l1_tasks` rows in the DB stay as history. No operational script reads that table.
- The 2,915 stranded articles return to the Article Lane queue. Running them is an operating decision, not automatic.
- The running `morninger` process must restart before the `l1_route` job stops.

### Current status (2026-10-06)

- In force. ADR-0016 (copy articles inherit results), ADR-0018 (single-paragraph citations) and ADR-0019 (thin articles leave the packet) amend it and declare the link.
- DSH, agy, opencode and other runtimes are interchangeable options for the Article Lane (FACT-llm-runtimes-are-interchangeable). The single-path rule and D4 to D6 still hold.

## Rollback

- Trigger: Article Lane fails acceptance in two consecutive waves.
- Restore files from `MANIFEST.json`, then restore the preset rows and the `morninger` job from git at the commit before this ADR.
- Then write a new ADR. No "temporary" fallback path is kept in code.

## Follow-up

- [x] US-026: remove preset rows and the `morninger` job, record tokens only (commit feb710c).
- [x] US-027: update `AGENTS.md`, registry and pipeline (commit bb47e44).
- [x] US-025: `--finish` fails loudly and checks DB write access before spending tokens (commit 77e166f).
- [ ] Operator decision on running the 2,915 stranded articles as a backlog wave.
