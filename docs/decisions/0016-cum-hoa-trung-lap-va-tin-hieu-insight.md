---
id: ADR-0016
type: adr
title: Story clustering, result inheritance and insight signals
status: accepted
lane: high-risk
created: 2026-10-02
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
approvers: [operator 2026-10-02]
story: [US-033, US-035]
amends: [ADR-0010]
related: [ADR-0012, ADR-0013]
evidence:
  - commit:fb9b1c2
  - commit:bfbd5e6
  - path:docs/proposals/20261001-dedup-architecture.md
  - path:docs/proposals/20261001-insight-analytics.md
  - path:project/src/pipeline/story_cluster.py
  - path:project/src/pipeline/inherit.py
  - path:project/scripts/signal_build.py
  - path:project/scripts/article_pack.py
  - test:project/tests/test_story_cluster.py
  - test:project/tests/test_inherit.py
  - test:project/tests/test_signal_build.py
  - metric:1314 articles in 3 days, 9 near-verbatim copies, 33 same-event articles (operational DB, 2026-10-01)
  - metric:8 article pairs with different titles and identical bodies (operational DB, 2026-10-01)
  - metric:transitive merge on shared ticker joined 10 distinct PNJ events into one cluster
  - operator:'"đồng ý triển khai trọn vẹn" for both proposals, 2026-10-02'
original: "commit:fb9b1c2"
reconstructed: 2026-10-06
summary: Cluster duplicate articles without deleting them; exact or 0.95-containment copies skip the model and inherit the canonical result as l1_source 'inherited'; derived signal tables measure coverage frequency and breadth.
summary_vi: Cụm hoá bài trùng mà không xoá bài; bài chép từ 0,95 trở lên kế thừa kết quả bài gốc, không tốn token; bảng tín hiệu đo tần suất và độ rộng đưa tin.
---

# ADR-0016 — Story clustering, result inheritance and insight signals

## Context

- Many outlets republish one event, and the Article Lane called the model once for every copy.
- Measured on the operational DB on 2026-10-01: 1,314 articles in 3 days, of which 9 were near-verbatim copies and 33 covered the same event as another article.
- Eight article pairs had different titles but identical bodies, because one source article id was republished under a new title and slug.
- Coverage frequency and breadth of a topic are investment signals, so duplicate articles MUST NOT be deleted (ADR-0013).
- Adding sources raises the duplicate rate, and tokens are spent on articles that add no information.

This was a Hard Gate decision. It adds DB tables, changes an Article Lane invariant of ADR-0010 and adds a new `l1_source` value. The operator approved both source proposals on 2026-10-02 with the words "đồng ý triển khai trọn vẹn". The proposals are `docs/proposals/20261001-dedup-architecture.md` and `docs/proposals/20261001-insight-analytics.md`. The ADR text names story US-033. The clustering code landed in commit fb9b1c2 labelled US-035, and the inheritance module landed in commit bfbd5e6 labelled US-033.

## Decision

- D1. Discovery ledger. Table `discovered_urls` MUST record every URL seen, before any filtering step. URL variants of one article live in `url_aliases`. The only terminal states are `captured`, `gone` and `dead_letter`.
- D2. Story clusters. Tables `story_clusters` and `cluster_members` record the role of each article: `canonical`, `copy` or `candidate`. Clustering MUST NOT delete or modify rows in `articles`.
- D3. Copy condition. An article MAY be marked `copy` only when its body matches exactly, or shingle containment is 0.95 or higher. The two lead-figure sets and the two ticker sets MUST also match. Very short articles MUST NOT be compared by shingles.
- D4. Result inheritance. A `copy` article MUST NOT enter a packet. Script `apply_inheritance` writes one `l1_outputs` row and one `agent_outputs` row with `l1_source = 'inherited'`, pointing to the canonical article through `inherited_from`. The value `inherited` counts as analysed; `code_first` stays excluded.
- D5. Hold copies for the canonical. The candidate selector holds a `copy` article for at most 48 hours after clustering. If the canonical has no result when the hold expires, the copy returns to the selector.
- D6. Amended invariant. The ADR-0010 invariant "every article is fully processed" now reads as two clauses. Every story is fully analysed once. Every article has a result and a role in a cluster. The 90% coverage threshold is unchanged, and its numerator includes inherited articles.
- D7. Derived signal tables. `signal_daily`, `entity_links` and `source_profile` are rebuilt entirely from `articles`, `l1_outputs`, `agent_outputs` and `cluster_members`. Script `signal_build.py` runs at 0 tokens and can drop and rebuild them.

### D8. Not implemented

The three items below are out of scope. Each one needs its own decision.

- Delta mode for `candidate` articles (P3). It changes the model output contract. Only a real model wave with operator sample review can verify it.
- Price cross-check (I3). It needs a price data source and a check of its terms of use.
- Flag `is_promotional` (I5). It changes the model contract.

## Alternatives

| Option | Why rejected |
|---|---|
| Delete or hide `copy` articles from `articles` | Violates ADR-0013 and loses the frequency signal. |
| Let the LLM decide technical copies | The question has a deterministic answer, so the model only adds token cost and variance. |
| Transitively merge every edge sharing a ticker | On real data it merged 10 distinct PNJ events into one cluster. |
| Let 0.8 rewrites inherit results | Verbatim citations of the canonical would no longer occur in the copy. |
| Vector DB and embeddings | A shingle index is enough for 2,000 to 5,000 articles per day. |

## Consequences

Gains:

- Verbatim copies cost no tokens and still carry a full result.
- Frequency, breadth and propagation speed of a topic are computable because every article is kept.
- Sensors, radar and delivery keep their counting rules, because they already filter on `l1_source <> 'code_first'`.

Costs accepted:

- If the canonical analysis fails, copies wait up to 48 hours. After the hold they are analysed on their own.
- The 0.95 threshold lets many rewrites through. They are still fully analysed, so only the saving is lost.
- The discovery ledger re-keys when a new source adds an article-id pattern. Command `capture_reconcile.py rekey` handles this.

### Current status (2026-10-06)

- D1 to D7 are implemented: `story_cluster.py`, `inherit.py` with `HOLD_HOURS = 48`, `signal_build.py` and the `--no-cluster` flag of `article_pack.py`.
- P3 remains open in `docs/OPEN-ITEMS.md` CAP-1 item 5. Item 6 of CON-1 records that the closed schema of ADR-0017 would reject the planned `same_event_as` field.
- I3 remains open in CAP-1 item 6. Until a price source exists, `signal_daily` measures press attention and tone, not trading signals.
- I5 is listed as not done in the insight proposal header and has no item in `docs/OPEN-ITEMS.md`.
- Delivery still emits copies as separate rows with inherited results (CAP-1 item 8).

## Rollback

- Stop clustering by removing the `run_story_cluster` call in `morninger` and by passing `--no-cluster` to `article_pack`.
- Delete `l1_outputs` and `agent_outputs` rows with `l1_source = 'inherited'` so copies return to the queue.
- The new tables are derived and can be dropped without affecting `articles`.
- The operator performs the rollback.

## Follow-up

- [ ] P3 delta mode: decide the output contract change and run one reviewed trial wave for `same_event_as`; amend the ADR-0017 schema first.
- [ ] I3 price cross-check: find an OHLCV source and verify its terms of use.
- [ ] I5 `is_promotional` flag: decide the model contract change and add an OPEN-ITEMS entry.
- [ ] Decide whether delivery groups rows by cluster, since it changes the delivery file structure.
