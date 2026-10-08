---
id: US-009
type: story
title: System-wide token burn optimization and L1 entity false-positive removal
status: retired
lane: normal
created: 2026-09-11
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
adr: [ADR-0005, ADR-0010]
related: [US-007, US-008]
evidence: ["commit:d119a8f", "path:project/src/agent/entities.py", "path:project/src/handoff/catalog.py", "test:project/tests/test_entities.py", "metric:37/37 targeted tests passed", "metric:947 of 1505 L1 articles selected, 37.1 percent Gold tokens saved"]
verify: "pytest tests/test_entities.py tests/test_pruner_and_batch.py tests/test_l1_router.py tests/test_user_output.py -v"
original: "commit:d119a8f"
reconstructed: 2026-10-06
summary: Subscriber-gated Gold export, a morphological guard for Vietnamese compound names, a 3-pass pruner and missed-only L1 routing cut token waste; the gate and lane were retired by ADR-0010.
---

# US-009 — System-wide token burn optimization and L1 entity false-positive removal

## Contract

- Gold export MUST pick only articles whose L1 entities sit in an active user's watchlist, so no Gold tokens go to articles nobody receives.
- L1 matching MUST NOT map Vietnamese compound place names, personal names or brands to `MACRO_GEO:MY`.
- The pruner MUST keep paragraphs with stock codes at the end of an article under a lower character ceiling.
- L1 routing MUST stop asking the model to re-review articles that code-first already resolved.

## Acceptance Criteria

- [x] `Capitalized Suffix Guard` and `Prefix Guard` in `src/agent/entities.py` drop every false positive of `MACRO_GEO:MY` on the 7,656-article DB while keeping all 300 real US macro articles.
- [x] `Catalog.claim` accepts `allowed_article_ids`; `AgentRunner.export_tasks` has `subscriber_only=True` by default; `agent_export.py` has `--subscriber-only` and `--no-subscriber-only`.
- [x] The pruner ceiling falls from 4,000 to 2,200 characters with a 3-pass algorithm, and `build_gold_input` passes `l1_entities` to it.
- [x] `l1_route.py --review` defaults to `missed`, and `run_agent_hierarchy.py` calls `l1_route.py --review missed` and `agent_export.py --subscriber-only`.
- [x] Targeted tests pass: 37/37.

## Design Notes

- Gold token leak: `agent_export.py` took every article with L1 regardless of subscribers. Measured: 483 of 1,274 articles (about 38%) ran Gold for nobody.
- Compound proper-noun trap: the alias "Mỹ" matched by regex `\bMỹ\b` hit compound place names ("Mỹ Thuận", "Mỹ Tho", "Mỹ Thủy").
- It also hit personal names ("Phạm Thị Mỹ Diệu") and brands ("Á Mỹ Grupo"), all mapped to `MACRO_GEO:MY`.
- Old pruner: the 4,000-character ceiling inflated input tokens, and the sequential early-break scan could miss stock-code paragraphs at the end.
- Old L1 routing: the default `--review all` made the model re-review 62% of articles already resolved by code-first.
- `Capitalized Suffix Guard` blocks the alias "Mỹ" when the next word is capitalized and absent from `_INTL_AFTER_MY` (`Trump`, `Biden`, `Fed`, `Wall Street`).
- `Prefix Guard` blocks the match when the previous word is a brand prefix ("Á", "Phú", "Phù") or a title ("Bà", "Ông", "Thị").
- `_context_guards.yaml` dropped compounds that collide with common words after folding (`my lam` collided with "Mỹ làm").
- The subscriber gate uses a SQLite temp table `_allowed_aids` and reads active users from `manifest.yaml`.
- The 3-pass pruner keeps up to the first 2 paragraphs (lead), then paragraphs with `l1_entities` codes or financial keywords, then fills in original order.
- Retired: ADR-0010 ended the two-tier L1/Gold lane, the subscriber gate, `l1_route.py` and `run_agent_hierarchy.py`. Every article is now fully processed.
- The morphological guard survives in the deterministic catalog matcher, used only to cross-check model results under ADR-0010.D4.
- Reconstructed: the `harness.db` row US-009 describes a different story ("Zero-Probe context and continuous learning protocol", 2026-09-15). The id was reused; this file is the 2026-09-11 story from commit d119a8f.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `pytest tests/test_entities.py tests/test_pruner_and_batch.py tests/test_l1_router.py tests/test_user_output.py -v` | passed, 37/37 |
| Integration | entity matcher run over 7,656 articles in `monocle.db` | `MACRO_GEO:MY` false positives down to 0; 300 real US macro articles kept |
| Platform | subscriber funnel on live data | 947 of 1,505 L1 articles selected; 558 dropped; 37.1% Gold tokens saved |

## Evidence

- Commit d119a8f (2026-09-11): "feat: token optimization, L1 precision & recall v2, and customizable gold export (ADR 0005, US-009/010/011)".
- Decision record: ADR-0005.
