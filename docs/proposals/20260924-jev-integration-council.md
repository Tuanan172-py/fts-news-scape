---
id: PRP-20260924-jev-integration-council
type: proposal
title: Integrate Jev (TypeSafe System One) as a post-finish typed verifier
status: parked
lane: high-risk
created: 2026-09-24
updated: 2026-10-06
lang: en
authors: [council-chair, claude-opus-5-5]
adr: []
story: []
plan: []
related: [ADR-0009, ADR-0010, PRP-20260923-agy-automation-council, PRP-20260924-jev-entity-linking-brainstorm]
evidence:
  - path:docs/proposals/20260924-jev-integration-council/research_A_jev_facts.md
  - path:docs/proposals/20260924-jev-integration-council/research_B_ecosystem_risks.md
  - path:docs/proposals/20260924-jev-integration-council/research_C_platform.md
  - path:docs/proposals/20260924-jev-integration-council/position_1.md
  - path:docs/proposals/20260924-jev-integration-council/rebuttal_3.md
  - path:project/scripts/article_pack.py
  - path:.agents/registry.yaml
  - commit:8ec12f8
  - url:https://docs.typesafe.ai/api.md
  - url:https://docs.typesafe.ai/models.md
  - metric:no Jev call was made by the council; all Jev quality claims are vendor or community sourced
original: "commit:8ec12f8"
reconstructed: 2026-10-06
summary: Should Jev, a typed classification model, join news-scape? Council recommends only a shadow, report-only post-finish verifier for citation support and ticker subject, gated by an offline Spike 0; parked.
summary_vi: Hội đồng đề xuất Jev chỉ làm bộ kiểm định hậu kỳ, shadow, sau Spike 0; chưa có quyết định, tạm gác chờ người vận hành.
---

# PRP-20260924-jev-integration-council — Integrate Jev (TypeSafe System One) as a post-finish typed verifier

Translated and condensed on 2026-10-06 from the Vietnamese council verdict of 2026-09-24. Full research, positions and rebuttals stay in the sibling folder [20260924-jev-integration-council/](20260924-jev-integration-council/). Labels: [V] verified on the machine by reading code only, [S] sourced, [I] inferred.

## Question

- Should news-scape integrate Jev (`jev-1.13.0`, TypeSafe AI System One), and if so, in which role and through which gates?
- Tier: high-risk, because it adds a new provider, a new API token and an exception to ADR-0009 D6. A registry cleanup part is normal tier.

## Findings

### Process

- Round 1 research: A (Jev product facts), B (ecosystem, calibration, injection, vendor risk), C (news-scape decision points, DSH and agy, governance, cost).
- Round 2 positions: P1 Jev as pre-pack ordering; P2 Jev as post-LLM verifier and router; P3 red team, "do not integrate this quarter".
- Round 3 rebuttals: P1 withdrew pre-pack ordering. P2 dropped materiality as sort key and `sent` from production. P3 withdrew "spike is tier 2" and "step 0 fills an ordering gap".
- Limit: nobody called Jev. No [V] claim about Jev behaviour exists.

### Load-bearing facts about Jev

| # | Fact | Label | Design consequence |
|---|---|---|---|
| J1 | Seed $40M, early access 2026-09-15, waitlist removed 2026-09-20; company under 10 days old | [S] | High vendor risk; the step MUST be optional and removable |
| J2 | Does not generate text. Three primitives: Noul (yes/no probability), Choice (at most 255 options, `probabilities` and `confidence`), Score (2 to 10 levels) | [S] | Cannot replace summary, implication, citation or open entity extraction. About 1,600 tickers exceed 255 options, so only per-candidate Noul works |
| J3 | `POST /v1/systemone`, Bearer key; no seed, temperature or batch endpoint; errors 401/422/429/529 | [S] | One request per article; determinism must be measured |
| J4 | 64k context per request; `state` plus longest question at most 32k; text only | [S] | One article fits |
| J5 | $0.042 per 1M input tokens, output free, early-access price; 250k tokens/s, 1,200 req/min | [S] | About $0.03 to $0.07 per day [I]; no token cap (ADR-0010) |
| J6 | English first; no Vietnamese measurement. Community audit: Russian -11 points (ECE 0.032 to 0.096), Korean -6.5, Spanish -3 to -6.4 | [S] | Decisive variable; a Vietnamese spike is the kill gate |
| J7 | ECE 0.107 in one study; 44.7% correct on unanswerable items at mean probability 0.74; removing "unknown" drops KoBBQ from 95% to 0% | [S] | Never use raw `confidence`; learn thresholds; always offer "unknown" |
| J8 | P(x) + P(not x) ranges 0.71 to 1.42; repeat calls std 0.001 to 0.015; option order can shift answers | [S] | Fix option order, log `option_order_hash`, measure flip rate |
| J9 | Self-declared weak at arithmetic, counting, dates, double negation, multi-step reasoning | [S] | Never ask Jev about numbers or dates |
| J10 | Prompt injection moved verdicts 0.76 to 0.48, and 96.5% to 26.5% on one audit | [S] | Jev only flags; spike includes 30 injected articles |
| J11 | Cloud only, no weights; ZDR enterprise only; processing region undisclosed | [S] | Hard ToS and DPA gate for the operator |
| J12 | `jev-latest` alias moves | [S] | Pin `jev-1.13.0`; log the returned model per row |
| J13 | Python SDK `typesafe-sdk` (Python 3.10+, sync and async) | [S] | Plain Python call, no framework |
| J14 | Open exits: Nokia AnyJev (Apache-2.0, same interface) and Laya (local multilingual mmBERT) | [S] | Control arm in Spike 0 and fallback |
| J15 | Vendor claims 193.6x faster and 444.6x cheaper; independent runs show about 2.9x and 12x | [S] | Vendor numbers MUST NOT be premises |

Open unknowns:

- Vietnamese financial accuracy and ECE.
- Whether `state` is billed once or per question. Cost could be off by xN.
- Whether Noul returns `confidence`.
- Region, retention, SLA, deprecation and a per-request question cap.
- AnyJev or Laya quality on Vietnamese.

### Decision-point map

Reference volume is about 350 articles per day (W365 had 365; 345 waited on 2026-09-23) [S]. Article Lane costs about $0.28 to $0.56 per day, so cost is not the deciding variable.

- D1 tier ordering inside a wave: low fit. `tier_of` runs after `LIMIT` [V `article_pack.py`]; nondeterministic order would break byte-identical packets and cache hits.
- D2 wave selector (SQL `ORDER BY published_at DESC ... LIMIT`): no fit; deterministic.
- D3 materiality: medium fit for measurement only. The lean output has no `m` field and `_sort_key` reads a score that is always 0; score is a secondary key after timestamp [V `user_output.py`].
- D4 sentiment, D5 time sensitivity, D6 entity group: low fit; DeepSeek already does them in the same pass at near-zero marginal cost, saving under $0.01 per day.
- D7 verify an attached ticker is the real subject: high fit. Noul over the closed set the LLM returned.
- D8 multi-source dedup tie-break: medium, deferred. D9 triage gate: no fit, violates ADR-0010. D10 deterministic DoD: no fit.
- D11 citation support check: high fit. Choice `supports/contradicts/says_nothing/unknown` per (paragraph k, claim). The only use case all three positions agreed on.
- D12 user routing, D13 spam label, D14 wave trigger, D15 daily brief: low or no fit.
- Conclusion [I]: moving classification from DeepSeek to Jev saves nothing; Jev value lies only in D7 and D11, which nobody checks today.

## Options

| Option | Benefit | Cost or risk |
|---|---|---|
| K: post-finish `cite_k` and `ent_<ticker>` verifier, shadow, report-only (chosen, conditional on Spike 0) | Catches two error classes the deterministic DoD and DeepSeek cannot check independently; touches no Article Lane invariant | New provider, key and ADR-0009 D6 exception; analyst review of 10 to 70 flags per day |
| Registry cleanup of `materiality-triage` and `adversarial-dod-verifier` to match ADR-0010 (chosen, first, no Jev) | Removes `pre-gold-gate`, `cost_budget` and gold KPIs that contradict "tokens are recorded" | About 0.5 day |
| Local control arm AnyJev or Laya on the same golden set (chosen in Spike 0) | Removes vendor and data-egress risk; fallback if ToS fails | Machine time |
| deepseek-flash self-check on the same questions (chosen, arm C) | No new vendor; if flash beats Jev by 15 or more precision points, drop Jev | About $0.3 to $0.5 |
| Add `m` to `agent-output-v2-lean` and change the xlsx sort key | Fills the materiality gap | Deferred: data contract change, separate high-risk intake; useless without a new sort key |
| Jev pre-pack ordering (`jev_triage.py`) | None measurable | Rejected; P1 withdrew. Overflow on 2026-09-23 was 45 articles (345 versus `--limit` 300); breaks cache |
| Jev as spam filter or depth cut | None | Rejected; violates "every article fully processed" |
| Jev replaces `sn`, `ts`, `e[1]` | Under $0.01 per day | Rejected; adds a vendor and shrinks the LLM-exclusive zone |
| Jev inside DSH `run_code` or as a DSH provider | None | Rejected; worker thread has no credentials, the key would leak to session logs, and the protocol is not text generation |
| Do nothing with Jev this quarter (P3) | Zero governance cost | Partly accepted: nothing reaches production (L2) this quarter |

## Recommendation

- R1. Run the registry cleanup first, without Jev.
- R2. Then run Spike 0 as reduced high-risk work: operator approves key and ToS; no ADR until the spike passes; at most 1 week; offline only.
- R3. Spike 0 golden set: 300 articles from W365 and 2026-09-23 files, 100 blind-labelled by FRA analysts with same-article hard negatives, about 300 synthetic negatives, 30 injected articles, and option-order permutation. Arms: A Jev, B AnyJev or Laya, C deepseek-flash.
- R4. Pass requires all of these:
  - `cite_k` AUROC at least 0.85 on hard negatives, and flag precision at least 50%.
  - Flip rate at most 5%, and injection delta at most 10 points.
  - Calibrated ECE at most 0.08, and Jev within 15 precision points of arm C.
  - Acceptable ToS and DPA.
- R5. Kill on any one of these:
  - `cite_k` and `ent` AUROC both below 0.75, or flip rate above 10%.
  - Injection shifts above 20% of articles, or flag precision below 30%.
  - Arm C ahead by 15 precision points.
  - Per-question billing pushes Jev cost above daily Article Lane cost.
  - Price change, over 1 week, or no ToS.
  - A ToS kill with arm B passing switches to AnyJev or Laya.
- R6. Estimated spike cost: about 6M tokens, about $0.25 for Jev [I]; analyst labelling about 6 to 10 hours [I]; dev 3 to 5 days.
- R7. Only after a pass: L1 shadow for 14 days, writing `data/qa/jev/<wave>.jsonl` after `--finish`, never a gate. Pass: precision at least 50% on 50 flags, flag rate 3% to 20%, skipped rate at most 5%. Kill: precision below 30%, flag rate below 1% or above 35%, model drift.
- R8. L2 (table `jev_verdicts`, read-only `jev_flag` column) is out of this quarter.
- R9. Jev MUST NEVER drop articles, reorder the selector, overwrite `agent_outputs`, gate `--finish` or count as "analyzed".
- Residual disagreements kept open:
  - Spike 0 tier. The chair chose reduced high-risk.
  - AUROC kill 0.75 versus 0.70. The chair chose 0.75.
  - The determinism threshold, and whether to measure `mat`.
  - The wording of any ADR-0009 D6 exception. The chair would pin vendor, model, version and role.
  - Whether Jev is worth it when the real flag rate is under 1%.

## Outcome

- No decision taken; parked on 2026-10-06 pending operator.
- No ADR followed. No story was opened for Jev. The provisional story numbers US-028 to US-031 in the original text were later used for unrelated stories.
- Executed: nothing. No `jev_verify.py` or `jev_shadow_eval.py` exists, no Jev commit exists after the proposal commit `8ec12f8`, and `plans/20260924-research-council-execution/plan.md` does not mention Jev.
- The registry cleanup step (R1) was not executed: `.agents/registry.yaml` still carries `stage_role: pre-gold-gate`, `gold_burn_reduction_pct` and `post-gold-qa` on 2026-10-06 (reconstructed 2026-10-06).
- Operator decisions still open:
  - H1 priority versus other work under WIP=1. H2 Spike 0 tier.
  - H3 key ownership and acceptance of non-ZDR data egress. H4 analyst labelling time.
  - H5 ADR approval before L1. H6 separate intake for `m` and the sort key. H7 running arm C.
