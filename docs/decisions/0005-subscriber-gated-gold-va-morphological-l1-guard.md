---
id: ADR-0005
type: adr
title: Subscriber-gated Gold export and morphological L1 guard
status: accepted
lane: normal
created: 2026-09-11
updated: 2026-10-06
lang: en
authors: [operator]
approvers: ["operator (date unrecorded)"]
story: [US-009]
evidence:
  - commit:d119a8f
  - commit:bb47e44
  - commit:eeccd9f
  - path:project/src/agent/entities.py
  - path:project/src/agent/pruner.py
  - path:project/config/entities/aliases/_context_guards.yaml
  - path:docs/stories/US-009-token-optimization-subscriber-gate-morphological-l1.md
  - metric:483 of 1,274 Gold articles (~38%) had no active subscriber, monocle.db 2026-09-11
  - metric:MACRO_GEO:MY false positives on 7,656 articles from 14 to 0
  - metric:subscriber filter kept 947 of 1,505 L1 articles, 558 skipped
  - test:pytest test_entities.py test_pruner_and_batch.py test_l1_router.py test_user_output.py, 37 of 37 passed
original: "commit:d119a8f"
reconstructed: 2026-10-06
summary: Four token and precision fixes for the L1/Gold lane - Prefix and Capitalized Suffix guards for ambiguous aliases, subscriber-gated Gold export, a 3-pass 2,200-character pruner, and L1 review of missed articles only.
summary_vi: Bốn cải tiến cho lane L1/Gold gồm guard tiền tố và hậu tố viết hoa cho alias "Mỹ", chỉ chạy Gold cho bài có người theo dõi, pruner 3 lượt trần 2.200 ký tự, và L1 chỉ duyệt bài code-first bỏ sót.
---

# ADR-0005 — Subscriber-gated Gold export and morphological L1 guard

## Context

- Gold token leak (~38%). `AgentRunner.export_tasks` picked every `work_item` with `l1_outputs.dod_pass=1`. It never checked whether the article's entities were on the watchlist of any active user.
- Measured on `monocle.db`: 1,274 articles had run Gold at a cost of millions of tokens, but only 791 were delivered to the active user `AnPT`. 483 articles (~38%) burned tokens for nothing.
- Vietnamese compound proper-noun trap in L1. In Vietnamese, spaces separate syllables, not words.
- The word-boundary regex `\bMỹ\b` matched compound place names ("Mỹ Thuận", "Mỹ Tho", "Mỹ Thủy", "Mỹ Lâm"). It also matched person names ("Phạm Thị Mỹ Diệu") and brands ("Á Mỹ Grupo"). All were tagged `MACRO_GEO:MY` (the United States).
- Result: news went to the wrong user watchlists, and the Gold agent burned tokens analysing "US economic implications" for a domestic road and bridge project.
- Pruner limits in `pruner.py`. The 4,000-character ceiling was too high for Vietnamese financial news, which follows the inverted pyramid.
- The old pruner walked paragraphs in order and stopped at the ceiling. It could drop late paragraphs holding tickers or figures when early paragraphs were generic commentary.
- L1 `--review all` wasted tokens. The default made the LLM re-read 1,108 articles (62%) that code-first had already resolved correctly.

## Decision

- D1 (part A). Remove L1 false positives with morphological and prefix guards (0 token). `_blocked_by_morphology` runs on the original string, instead of relying only on the manual `block_in` blacklist. That blacklist collides after diacritic folding, as "Mỹ Lâm" folds to `my lam` and overlaps "Mỹ làm".
  - D1.1 Capitalized Suffix Guard. After "Mỹ", if the next word is capitalized and not in `_INTL_AFTER_MY`, the match MUST be rejected. Examples of the next word: `Thuận`, `Tho`, `Đình`, `Thủy`, `Lâm`, `Diệu`, `Phước`. `_INTL_AFTER_MY` holds words such as `Trump`, `Biden`, `Fed`, `Wall Street`.
  - D1.2 Prefix Guard. The match MUST be rejected if the previous word is a brand prefix (`Á`, `Phú`, `Phù`, `Bắc`, `Nam`). The same applies to a title or name part (`Bà`, `Ông`, `Thị`, `Văn`, `Cô`, `Chị`).
  - Claimed effect: 100% of place-name and person-name false positives removed, 100% of genuine United States mentions kept.
- D2 (part B). Subscriber-gated Gold export in `AgentRunner.export_tasks` and `Catalog.claim`.
  - Only `work_items` whose `l1_entities` intersect the watchlist of at least one active user (`manifest.yaml` and `users/*.yaml`) MAY be picked.
  - Filtering MUST be atomic through the SQLite temporary table `_allowed_aids`.
  - Articles without a follower stay intact in state `L1_ONLY`, ready when a new user appears (lazy, on-demand enrichment).
  - Claimed effect: ~38% to 45% of total Gold tokens saved.
- D3 (part C). Semantic pruner, 3 passes, 2,200 characters maximum.
  - The default ceiling drops from 4,000 to 2,200 characters.
  - Pass 1 always keeps up to the first 2 paragraphs (lead). Pass 2 scans the whole article and prioritizes paragraphs holding tickers from `l1_entities` or financial figures.
  - The Pass 2 financial markers are `%`, `tỷ đồng`, `lợi nhuận`, `doanh thu` and `kế hoạch`. Pass 3 fills remaining paragraphs in original order up to 2,200 characters.
  - Rule 05 invariant preserved: whole `<p>` blocks are kept, so `citations` stay exact substrings for the DoD gate.
  - Claimed effect: ~45% fewer input tokens per article sent to the Gold subagent.
- D4 (part D). L1 routing defaults to `--review missed` in `l1_route.py` and `run_agent_hierarchy.py`. `resolved` articles are materialized directly through `l1_ingest.py --code-first` (0 token). Claimed effect: 62% fewer L1 tokens.

## Alternatives

| Option | Why rejected |
|---|---|
| Status quo: manual `block_in` blacklist for ambiguous aliases | Collides after diacritic folding ("Mỹ Lâm" to `my lam` overlaps "Mỹ làm"); original part A. |
| Status quo: export every L1-passed article to Gold | 483 of 1,274 Gold articles (~38%) had no active subscriber (original Context). |
| Status quo: sequential pruner with a 4,000-character ceiling | Too large for inverted-pyramid news and drops late paragraphs with tickers or figures (original Context). |
| Status quo: L1 `--review all` | Re-reads 1,108 articles (62%) already resolved by code-first (original Context). |

## Consequences

Measured results recorded in the original (commit d119a8f):

- Test suite: 37 of 37 passed.
- False positives on 7,656 articles in `monocle.db`: from 14 cases to 0.
- Subscriber filter: 947 of 1,505 articles have a follower; 558 articles skip Gold.
- Estimated total token saving across the system: 60% to 70%. This is an estimate, not a ledger measurement.

Costs accepted:

- Articles without a follower get no Gold analysis until a user subscribes (D2).
- Content beyond 2,200 characters is not seen by the Gold model (D3).

### Current status (2026-10-06)

- D1: in force. `_blocked_by_morphology` and `_INTL_AFTER_MY` remain in `project/src/agent/entities.py`, used by the catalog matcher that cross-checks model output (ADR-0010).
- D2: dead. ADR-0010 retired Gold export; `AGENTS.md` §6B states that subscriber-gated filtering no longer exists and every article is fully processed.
- D3: dead for the live lane. The Article Lane packet reads full content; the distillation ceiling was set to 0 by commit eeccd9f. The 2,200 default remains only in the retired Gold packet code.
- D4: dead. ADR-0010.D2 removed `l1_route`, and ADR-0010.D4 excludes `code_first` output from every analysed count.

## Rollback

- Each part reverts independently with `git revert` of the touched lines from commit d119a8f.
- D2 had a runtime switch: `agent_export.py --no-subscriber-only` (reconstructed from `docs/stories/US-009-token-optimization-subscriber-gate-morphological-l1.md`).
- D4 could be undone by passing `--review all` explicitly.

## Follow-up

- [ ] Verify the 60% to 70% token saving estimate against a ledger. Obsolete for D2 to D4 since ADR-0010.
- [ ] Keep the D1 guards covered by `project/tests/test_entities.py` while the catalog matcher remains in use.
