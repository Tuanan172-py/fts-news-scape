---
id: PRP-20260924-jev-entity-linking-brainstorm
type: proposal
title: Jev for L1 entity linking of headlines into the entity store
status: parked
lane: high-risk
created: 2026-09-24
updated: 2026-10-06
lang: en
authors: [council-chair, claude-opus-5-5]
adr: []
story: []
plan: []
related: [ADR-0009, ADR-0010, PRP-20260924-jev-integration-council]
evidence:
  - path:docs/proposals/20260924-jev-entity-linking-brainstorm/ideas_A.md
  - path:docs/proposals/20260924-jev-entity-linking-brainstorm/ideas_B.md
  - path:docs/proposals/20260924-jev-entity-linking-brainstorm/ideas_C.md
  - path:docs/proposals/20260924-jev-entity-linking-brainstorm/ideas_D.md
  - path:docs/proposals/20260924-jev-entity-linking-brainstorm/critique_F.md
  - path:docs/proposals/20260924-jev-entity-linking-brainstorm/critique_G.md
  - path:project/scripts/article_pack.py
  - commit:8ec12f8
  - wave:W365
  - metric:206 of 206 measured "unlisted but in store" misses in W365 came from malformed group codes (critique_F)
original: "commit:8ec12f8"
reconstructed: 2026-10-06
summary: Can Jev link headline entities to the entity store? Only as a closed-set verifier after the LLM; the largest gain needs no Jev, so a zero-token Spike -1 comes first; parked.
summary_vi: Jev chỉ có thể làm bộ kiểm chọn trong tập đóng sau LLM; phần lợi lớn nhất không cần Jev; chưa có quyết định, tạm gác chờ người vận hành.
---

# PRP-20260924-jev-entity-linking-brainstorm — Jev for L1 entity linking of headlines into the entity store

Translated and condensed on 2026-10-06 from the Vietnamese brainstorm of 2026-09-24. It was a brainstorm, not a proposal ready for decision. Idea and critique papers stay in [20260924-jev-entity-linking-brainstorm/](20260924-jev-entity-linking-brainstorm/). Predecessor: [PRP-20260924-jev-integration-council](20260924-jev-integration-council.md). Labels: [S] sourced, [V] verified read-only, [I] inferred. No Jev API was called; every Jev number is [I] until measured.

## Question

- Input: a Vietnamese financial headline, optionally with 1 to 2 lead paragraphs.
- Can Jev help link every mentioned entity to an `entity_id` in `project/data/entities/entities.json` (1,262 entities, 1,093 tickers) or to NIL?
- Can it tell which entity is the subject?

## Findings

### Hard constraints

- C1. Entity extraction belongs to the LLM `article-processor`; Jev may only check, never generate.
- C2. Deterministic matching only verifies; Jev output MUST NOT enter `l1_outputs` or `agent_outputs` or change coverage counts.
- C3. ADR-0009 D6 says every agent route is `deepseek-flash`; Jev SaaS or AnyJev at runtime needs an ADR amending D6.
- C4. A new provider, API token or DB schema change is high-risk tier.
- C5. Every article is fully processed; Jev MUST NOT filter, cut depth or block delivery. Tokens are recorded, not gated.
- C6. One wave is one `run_code`; Jev runs only after `--finish`, and its failure MUST NOT change the exit code.
- C7. Jev limits [S]: Choice at most 255 options; 32k for state plus longest question, 64k total; no span extraction; no native multi-label; P(yes) is not 1 - P(no); option-order sensitive; no seed; no Vietnamese measurement. So 1,093 tickers need a top-K candidate generator and two permutations.
- C8. User watchlists MUST NOT go into state or options.

### Key results

- K1. Jev cannot recognize entities, only adjudicate a closed set. Some other component MUST generate candidates: LLM mentions plus code lookup.
- K2. The biggest gain needs no Jev [V critique_F]: 206 "unlisted but in store" pairs in W365 all came from the LLM writing malformed group codes (`ASSET_CLASS:`, `MACRO_GEO`, `IND_GICS3:`), which `IntentResolver` drops. Fixing group-code normalization and an alias learning loop (Novaland, Vinaconex, KienlongBank, PVCFC) costs 0 tokens.
- K3. Jev keeps only narrow closed-set niches: ambiguous alias resolution with entity cards, subject role of a ticker in the headline (D7 of the previous council), and ranking the alias review queue. GICS3 industry is a minor fourth.
- K4. A governance hole MUST be fixed first [V critique_G]: the wave selector uses a blacklist (`l1_source <> 'code_first'` in `scripts/article_pack.py`). Any new `l1_source` value such as `jev` or `relinked` would count as "analyzed". Switch to a whitelist `l1_source = 'agent'`, with or without Jev.
- K5. Pros of Jev:
  - It fits "choose from a closed set" with a NONE option.
  - Options carry negative knowledge (`what`, `not_for`, `examples`).
  - Cost is about $0.042 per 1M input tokens and latency 70 to 500 ms. A wave costs under $0.05 with two permutations [I].
  - It is a model family independent from deepseek-flash. AnyJev offers the same interface under Apache-2.0.
  - GICS1/2/3 (11/28/51) and 37 macro entities fit one question.
- K6. Cons:
  - Recall is capped by the candidate generator.
  - No world knowledge outside options, such as Vinaconex as parent of V21/VCC or TCBS under TCB.
  - Calibration is hard to threshold.
  - No seed. Putting it in `detect()` turns stable errors into random ones.
  - Literal reading, and context rot with long options. A 237-ticker shard is about 9k to 13k tokens.
  - Prompt injection via third-party RSS headlines, heavy governance and low marginal value.

### Idea map (feasibility, value, risk on 1 to 5)

| Code | Idea | Jev needed | F / V / R | Maturity |
|---|---|---|---|---|
| N0 | Normalize group codes in `IntentResolver`; expose `setdefault` ambiguity | No | 5 / 5 / 2 | ready to test |
| N1 | Whitelist `l1_source = 'agent'` in selector and coverage | No | 5 / 5 / 1 | ready to test |
| L1 | Static entity cards built from `entities.json` and `_context_guards.yaml` | No (code) | 5 / 4 / 1 | ready to test |
| L2 | Reviewed alias learning loop; Jev only ranks | Optional | 5 / 4 / 1 | feasible |
| L3 | Post-finish linker: mention to top-K (K at most 20) to Jev choice plus `NONE_IN_KB` | Yes | 4 / 2-3 / 2 | feasible |
| L4 | Ambiguous or common-word alias resolution | Yes | 4 / 3 / 2 | feasible |
| L5 | Subject role SUBJECT / SECONDARY / CONTEXT, also disagreement arbiter | Yes | 4 / 4 / 3 | feasible |
| L6 | One GICS3 question for article industry and unlisted industry | Yes | 4 / 3 / 3 | ready after N0 |
| L7 | Noul over 37 macro, institution and index entities | Yes | 3 / 2 / 3 | idea |
| L8, L9 | Jev versus morphology guards; bare industry alias recovery | Measure only | 4 / 2 / 4; 3 / 2 / 4 | measure only |
| L10 | Parent, subsidiary and brand relations | Yes | 2 / 3 / 2 | blocked: store lacks `parent` |
| L11 | Embedding retrieval, Jev re-rank | Yes | 3 / 2 / 2 | idea |
| M1 | Multi-system calibration bench | Offline | 4 / 5 / 1 | feasible |
| X1 to X4 | GICS1 shard tournament; tiered search; pairwise event dedup; Jev before LLM | - | - | rejected |

- Rejected reasons:
  - X1 costs about 100k tokens per article and turns Jev into a parallel recognizer.
  - X2 propagates errors across 4 sequential 500 ms calls.
  - X3 fails on numbers ("700 tỷ" versus "500 tỷ" are two events).
  - X4 anchors the LLM and runs before the conductor session.
  - Removing deterministic guards is rejected because they fire on only 0.9% of headlines.
- Three concepts are detailed in the original text: post-finish linker with entity cards (L1, L3, L4), subject role arbiter (L5; W365 had 289 LLM-only tickers), and reviewed alias loop (L2). Missing aliases verified: NVL "Novaland", VCG "Vinaconex", KLB "KienlongBank", DCM "PVCFC", TCX "TCBS", DSE "DNSE"; noisy aliases: "Đại Dương" to OGC, "Quốc Dân" to NVB.

### Disagreements kept open

- The 26% figure: ideator D counted 578 of 2,206 strings as unlisted-but-in-store (365 articles). Critic F found 206 of 206 measured misses were malformed codes, on 92 parsed records and 549 pairs. Bases differ; Spike -1 MUST fix one base.
- Whether relinking needs an ADR (D yes, F no, G a short ADR with a separate `relinked_exact` label). The brainstorm leaned to G.
- Jev replacing guards (B) versus value 2 and risk 4 (F, G); `drop_bare` recall loss remains unmeasured.
- Injection risk: B "near zero", G not; the brainstorm followed G.
- GICS3 value, whether local AnyJev escapes high-risk tier at runtime (G: no), and whether ADR-0009 D6 covers "every model" or only DSH agent routes.
- Shared alias key count: 60 (B) versus 54 (F), different counting methods.

## Options

| Option | Benefit | Cost or risk |
|---|---|---|
| E0 Spike -1: group-code normalization, candidate list instead of `setdefault`, whitelist `l1_source = 'agent'`, regression tests | Largest measured gain; closes the governance hole; 0 tokens | Normal tier; selector change touches coverage semantics, so operator review |
| E1 headline golden set, about 320 pairs, 2 labellers plus 1 arbiter with Cohen kappa | Single ground truth for every later step | Human labelling effort |
| E2 entity cards for 30 confusable entities; E3 alias loop without Jev | Better curator queue at 0 tokens | Curator review of `not_for` |
| E4 offline calibration bench: baseline after E0, alias lookup, deepseek-flash, local AnyJev | Decides whether Jev adds value at all | Local machine and deepseek-flash tokens |
| E5 Jev SaaS shadow on real waves | Real shadow records | High-risk: ADR amending D6, vendor ADR, API token; under $0.05 per wave [I] |

## Recommendation

- R1. Run in order: E0, E1, E2, E3, E4; reach E5 only after an ADR amending ADR-0009 D6.
- R2. E4 kill thresholds. Any one stops the Jev or AnyJev arm:
  - k1: F1 on hard tiers is not at least 5 points above baseline.
  - k2: ECE above 0.08, or not better than deepseek-flash.
  - k3: over 10% of pairs with option-order delta P above 0.15.
  - k4: Vietnamese accuracy more than 5 points below the English translation.
  - k5: p95 above 800 ms per article, or any injection passing the 20-headline red set.
- R3. For L5: if deepseek-flash agrees with human labels above 90%, add `role` to the LLM schema instead of a verifier.
- R4. After E4: AnyJev passing alone stays an offline curator tool; Jev and AnyJev clearly beating deepseek-flash justifies the D6 ADR and E5; a tie means no new model.
- R5. Jev labels MUST only rank review queues, propose alias or guard PRs for human review, or fill an information column. Every shadow row logs provider, version, `option_order_hash` and raw probabilities of both permutations.

## Outcome

- No decision taken; parked on 2026-10-06 pending operator.
- No ADR followed and no story was opened.
- Executed: nothing. `project/scripts/article_pack.py` still defines `ANALYZED_L1` with the blacklist `COALESCE(o.l1_source, 'agent') <> 'code_first'` on 2026-10-06, so N1 and E0 were not done. No Jev commit exists after `8ec12f8`, and `plans/20260924-research-council-execution/plan.md` does not mention Jev (reconstructed 2026-10-06).
- Open operator questions:
  - Q1 whitelist `l1_source` now. Q2 how relinked lookups are recorded. Q3 scope of ADR-0009 D6.
  - Q4 AnyJev at runtime. Q5 who labels about 320 pairs.
  - Q6 a `parent` field in the entity store, a data contract change. Q7 `role` in `l1-entity-output-v1`.
  - Q8 shadow table `entity_link_check` versus JSONL. Q9 card language.
