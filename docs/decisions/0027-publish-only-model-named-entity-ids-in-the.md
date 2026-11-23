---
id: ADR-0027
type: adr
title: Publish only model-named entity ids in the entities column
status: accepted
lane: high-risk
created: 2026-11-14
updated: 2026-11-15
lang: en
authors: [agent]
approvers: [operator 2026-11-15]
story: []
supersedes: []
amends: []
evidence:
  - "metric: entities equals intent_code on 99.4% of 691 articles, partition 2026-11-13 (fpa-toolkit branch task/news-entity-severity-notes, findings 6.1)"
  - "metric: entities precision 15% against a two-seat cross-reviewed gold set of 40 stories; intent_llm 48% overall, 80% for tickers (findings 6.4)"
  - "metric: the rule replayed on the same 40 stories lifts entities precision from 0.15 to 0.48 and ticker precision from 0.17 to 0.80; recall falls from 0.92 to 0.76 (168 false ids dropped, 6 true matcher-only ids lost) (findings 7.1)"
  - "test: project/tests/test_lakehouse_model_entities.py"
summary: The entities column keeps only ids the model named; ids the deterministic matcher found alone stay in intent_code. Enforced at ingest and at dropzone consolidation, so every producer follows it.
summary_vi: Cột entities chỉ giữ thực thể do mô hình nêu; thực thể chỉ bộ đối chiếu tìm thấy vẫn nằm trong intent_code.
---

# ADR-0027 — Publish only model-named entity ids in the entities column

## Context

- On partition 2026-11-13, `entities` equals `intent_code` (the deterministic matcher's ids) on 99.4% of 691 articles and `intent_llm` on 51.2%.
- 231 articles carry tickers only the matcher found; examples: MBB and MDG on "Những sai lầm chết người của Ukraine", API on a Google Search story, MBB on a story about a singer.
- Against a gold set labelled independently by two seats of different model families (40 stories, 38 agreed ids, 20 disputed ids excluded), `entities` is 15% precise; `intent_llm` is 48% precise overall and 80% for tickers.
- The rows came from the external dropzone (`dev_id antigravity`): the ingest normalizer and the consolidator pass a producer's `entities` through unchanged, so a producer that merges matcher ids reaches every reader.

AGENTS.md section 7 already says deterministic matching checks the model and never replaces it, and that no heuristic produces recognition results.
The published column breaks that rule, and every reader inherits the noise: the plugin's `article_entities` view, the fpa-toolkit all-hands triage, the `news-watch` skill and the per-user Excel delivery.

## Decision

1. D1: The `entities` column MUST hold only items whose id appears in the row's `intent_llm` (full `KIND:CODE` comparison with `[TYPE]` tags stripped; a bare code the model wrote without its kind matches that code).
2. D2: The rule MUST be applied in `sanitize_article_record` (ingest) and again after deduplication in `consolidate_dropzone`, because dropzone files can be written without the normalizer.
3. D3: Ids the matcher found alone MUST stay visible through `intent_code` and `intent_source`; the schema does not change.
4. D4: A row with both `intent_llm` and `intent_code` empty (no provenance, older records) MUST pass through unchanged.

## Alternatives

| Option | Why rejected |
|---|---|
| Add an `entity_provenance` column | Duplicates `intent_code` minus `intent_llm`; a schema change for no new information. |
| Fix only `publish.py` | The rows at fault come through the dropzone, which bypasses `publish.py`. |
| Filter in each reader | Four readers would each re-implement the rule; fpa-toolkit already had to (triage and news-watch), and new readers would repeat the bug. |

## Consequences

- Readers get the model's precision without their own filter; on the gold set that is 15% to 48% overall.
- Recall drops on ids only the matcher saw; on the gold set those were mostly wrong, but a real body mention the model missed disappears from `entities` (it stays in `intent_code`).
- Inferred sectors in `intent_llm` (12% precise) are not fixed by this rule; the sector rule in the article prompt, measured separately in the same change, addresses them.
- The plugin's `article_entities` view and every reader keep working unchanged.

## Rollback

Revert the two calls to `keep_model_entities` (ingest and consolidator) and re-consolidate the affected days from the dropzone archive; the operator or the repository owner may do it.

## Follow-up

- [x] Old-against-new evaluation on a frozen sample (tokens, precision and recall per kind), then set `status: accepted` with the approver (operator, 2026-11-15).
- [ ] Re-consolidate published partitions so history follows D1, after acceptance.
- [ ] Tell dropzone producers that matcher ids belong in `intent_code` only.
