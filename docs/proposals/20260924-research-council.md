---
id: PRP-20260924-research-council
type: proposal
title: Research council on design and growth headroom
status: parked
lane: normal
created: 2026-09-24
updated: 2026-10-06
lang: en
authors: [research council (6 agents), An Pham Thanh]
related: [ADR-0009, ADR-0010, ADR-0013, ADR-0015, US-025, US-026, US-027, US-028]
evidence:
  - path:plans/20260924-research-council-execution/plan.md
  - commit:8ec12f8
  - commit:18e6633
  - commit:a6a1583
  - commit:77e166f
  - commit:feb710c
  - commit:bb47e44
  - metric:about 1,566 hashes in seen_articles with no row in articles, 2026-09-24
  - metric:3,870 articles since 15/09, 763 analyzed (about 20%), median delay about 6 hours, 2026-09-24
  - metric:180 CONTENT_CHANGED versions never re-analyzed, 2026-09-24
  - metric:517 tests take 296 s, 2026-09-24
  - url:https://www.anthropic.com/engineering/building-effective-agents
  - url:https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf
  - url:https://hamel.dev/blog/posts/llm-judge/
  - url:https://hamel.dev/blog/posts/evals-faq/
  - url:https://api-docs.deepseek.com/quick_start/pricing/
  - url:https://api-docs.deepseek.com/guides/kv_cache/
  - url:https://arxiv.org/pdf/2402.10302
  - url:https://arxiv.org/pdf/2501.02237
  - url:https://arxiv.org/pdf/2404.10774
original: "commit:8ec12f8"
reconstructed: 2026-10-06
summary: Where is the largest growth headroom? Council kept the one-LLM-step workflow and ranked value-leak fixes, a golden set, body-entity routing and story clustering; no ADR followed, parked pending operator.
summary_vi: Hội đồng giữ workflow một bước LLM, xếp ưu tiên vá rò giá trị, golden set, phân tuyến thực thể thân bài và gom cụm; chưa có ADR, đang treo chờ người vận hành.
---

# PRP-20260924-research-council — Research council on design and growth headroom

## Question

- Is the current design right, and where is the largest headroom for growth?
- Method: six parallel read-only research agents, one scope each.
  - (1) data layer, (2) agent layer and Article Lane, (3) delivery and user value.
  - (4) harness and governance, (5) ADR and proposal history, (6) external practice 2024-2026.
- The coordinating session cross-checked findings and re-verified the most severe ones in code, marked `[checked]`.
- Update 2026-09-24 (operator decision): `materiality` and `event_type` are no longer used. Ranking and alerts below use only `time_sensitivity`, watchlist tier, cluster size and source count.

## Findings

### Executive conclusion

- The core architecture is right and SHOULD be kept. It is a deterministic workflow with exactly one LLM step: crawl, immutable Bronze, Silver, pack, `article-processor` in parallel batches, expand, DoD gate, delivery.
- In the Anthropic "Building effective agents" taxonomy this is prompt chaining plus parallelization, which matches industry practice for production systems.
- The bottleneck is not a missing agent. It is a measurement gap and value leaking at layer boundaries.
- The system measures quantity (coverage of at least 90%, clean ingest) but not correctness. No golden set, precision, recall or summary scoring exists, so every prompt, model or agent change is a guess.
- Headroom in order: fix value leaks (cheap) → golden set and eval (prerequisite for everything) → body entities in routing (high-risk) → a story layer that unlocks alerts, daily briefs, per-ticker timelines and RAG.
- Autonomous agents belong only at the edge: `entity-curator` (proposes catalog deltas, human approves) and `harness-auditor` (read-only). Clustering, verifier and brief SHOULD be fixed workflow steps.

### Value leaks, upstream to downstream

| Id | Leak | Evidence | Effect |
|---|---|---|---|
| L1 | Fuzzy dedup drops articles, even against the same source | `src/core/base_scraper.py:70` passes "cafef" while `seen_articles.source_domain` holds "cafef.vn"; `dedup.py:92` filters `!=`; `token_set_ratio`=100 when a title is a subset [checked] | About 1,566 hashes in `seen_articles` with no row in `articles`, including CBTT titles such as "VHM: CBTT…"; no Bronze, so not recoverable |
| L2 | Edited articles are never re-analyzed | `articles` uses INSERT OR IGNORE by url; selector picks an arbitrary `package_path` (`article_pack.py:185-193`) | 180 `CONTENT_CHANGED` versions skipped |
| L3 | Body entities and inferred sectors are discarded | `article_expand.py:197` keeps only `e.in_title and e.surface in title`; `article_mentions/*.json` is write-only [checked] | The value the prompt calls unique to the model is excluded from watchlist routing |
| L4 | Few-shot teaches a wrong sector | Example tags a Hoa Phat steel article as road and rail transport (`build_article_prefix.py:300`) [checked] | Systematic sector noise |
| L5 | Backfilled citations are not model-chosen | Under 2 indexes, the script adds the first long paragraph (`article_expand.py:281-288`), not sorted as the comment claims [checked] | Evidence may not support the claim; grounding DoD trivially passes |
| L6 | Articles failing the content layer are stuck forever | Selector reads only `l1_outputs`, which always exist (`article_pack.py:190-192`) | Up to 10% per wave never rerun |
| L7 | No materiality or event_type | Retired by the operator 2026-09-24 | Closed |
| L8 | xlsx hides the strength | No citations column; 3 technical Intent columns lead (`xlsx_delivery.py:16-36`) | Verbatim citations never reach the analyst |
| L9 | Sparse waves, low coverage | Since 15/09: 3,870 articles, 763 analyzed (about 20%); no waves on 19, 20, 22/09; last delivery 21/09; median delay about 6 hours | Analysts receive nothing for days |
| L10 | The old lane still runs | `project/scripts/run_daily.ps1:96-105` calls `l1_route`, `l1_ingest --code-first`, `agent_export` [checked] | Can recreate the ADR-0010 defect |

- Operational risks:
  - Bronze (2.1 GB) and Silver sit in OneDrive with cwd-relative paths; 478 MB landed in `project/src/data/`.
  - 2 OneDrive conflict DB copies exist; `settings.yaml:3` points to a dead 187 MB DB.
  - `project/data/archive/` (3,350 files) is not ignored; 25 files are uncommitted (+1,064/−846).
- Documentation drift:
  - simhash64 is computed but unused by `change_detect.classify`.
  - `charter.md` describes WSL, ClickHouse, Telegram and 1 user; the system runs Windows, OneDrive, SQLite and 5 users.
  - `harness_cli.py:294` defaults `unit_proof or 1`, so H4 does not block unverified stories.
- Harness: 16 documents, 9 rules, 18 skills, about 60 okf files, 15 plans and 7 proposals for one person and one lane; `audit` health 0.15 measures process, not product quality; `agent_metrics` has no row for `article-processor`.
- Cost levers without token gates:
  - The DeepSeek price page read on 24/09 showed peak price doubled 08:00-11:00 and 13:00-17:00 Vietnam time on workdays.
  - Off-peak runs would halve cost; the page MUST be re-checked before changing the schedule.
  - Byte-identical prefixes across batches, with cache-hit tokens logged; clustering before pack.

### Where intelligence belongs (summary)

- Keep pack → LLM → expand → ingest. Add a separate fast cadence for tier 1.
- `--repair` becomes a bounded one-round evaluator-optimizer (fixes L6). `adversarial-dod-verifier` samples 5% per wave plus 100% of urgent watchlist articles, report only.
- `story-dedup-clusterer`: simhash LSH plus bge-m3 embeddings, LLM only on edge cases, before pack. `daily-brief-synthesizer`: per-user map-reduce, every point anchored to `article_id`.
- Model cascade flash → pro only when eval proves benefit; high-risk because it changes ADR-0009 D6.
- Detailed per-layer backlog (data, agent, user, harness) with effort sizes is in [plans/20260924-research-council-execution/plan.md](../../plans/20260924-research-council-execution/plan.md).

## Options

| Option | Benefit | Cost or risk |
|---|---|---|
| A. Phased roadmap: 0 (this week) fix L1, L4, L5, remove old lane, move paths out of OneDrive; 1 (2-3 weeks) golden set, eval, body-entity ADR, L6, xlsx, cadence; 2 (1-2 months) clustering, verifier, brief, alerts; 3 structured sources, curator, cascade, RAG | Measurement first, then value; fixes data loss now | Needs 6-10 analyst hours for labels and two high-risk ADRs |
| B. Add more autonomous agents on the delivery path | Visible new capability | No metric to judge them; repeats the gate-then-remove cycle seen 5 times in ADR-0003 to ADR-0010 |
| C. Keep the system as is | No effort | Ongoing data loss (L1), 20% coverage, citations never delivered |

- Lessons that constrain every option:
  - No new gate, cap or filter without measurement. No script replacing LLM work (happened 3 times).
  - Never trust exit codes: `l1_ingest.py:94` and `agent_ingest.py:75` always return 0.
  - No old lane kept "for rollback". No ADR or story number reserved in a proposal.

## Recommendation

- Option A. The golden set of 150-200 articles and a 0-token `scripts/eval_article.py` serve the internal eval, JEV Spike 0 and any agy A/B comparison.
- Proposed order (H6): H1 commit US-025 to US-027 → US-028 → phase 0 → golden set → body-entity ADR → JEV Spike 0 → agy A/B.
- Operator decisions requested:
  - H1 commit US-025 to US-027; H2 open the body-entity routing ADR; H3 fund 6-10 analyst hours of labeling.
  - H4 run the 2,915-article backlog of 10-17/09 or not; H5 move waves off peak; H6 ordering.

## Outcome

- No decision taken; parked on 2026-10-06 pending operator.
- No ADR adopted the roadmap. The execution plan `plans/20260924-research-council-execution/plan.md` still says "chờ duyệt" (awaiting approval) with no agent assigned.
- Executed from it (reconstructed from git log on 2026-10-06):
  - T-00: `materiality`, `event_type` and `impact_area` removed from delivery output (commit 18e6633).
  - H1: US-025, US-026 and US-027 committed (commits 77e166f, feb710c, bb47e44).
  - T0.2: archive and OneDrive conflict copies ignored in git (commit a6a1583).
  - Proposal and plan recorded in commit 8ec12f8.
- Finding L1 (CBTT titles lost to fuzzy dedup) reserved ADR-0015, which was rejected as absorbed when ADR-0013 removed crawl-layer fuzzy dedup.
- Golden set, eval script, body-entity ADR, clustering per this proposal and the model cascade have no linked decision from this proposal.
