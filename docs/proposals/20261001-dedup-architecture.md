---
id: PRP-20261001-dedup-architecture
type: proposal
title: Multi-source duplicate article handling architecture
status: decided
lane: high-risk
created: 2026-10-01
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
adr: [ADR-0016, ADR-0013]
story: [US-033]
plan: []
related: [ADR-0015, PRP-20261001-insight-analytics]
evidence:
  - commit:579163c
  - "metric:monocle.db read-only, window 2026-09-28 to 2026-10-01, 1,759 rows in articles, 2,074 rows in seen_articles"
  - metric:439 articles dropped by crawl-layer fuzzy dedup in 3 days, 202 (46%) wrongly
  - metric:67 of 1,742 redundant clusters at containment >= 0.8 (3.8%); 136 of 1,742 at >= 0.5 (7.8%)
  - metric:SimHash present on 138 of 1,759 articles (8%)
  - metric:1,461 Bronze files stuck in Silver dead-letter
  - metric:3,120 of 11,591 articles since 2026-09-01 have a model result (27%)
  - path:docs/OPEN-ITEMS.md
original: "commit:579163c"
reconstructed: 2026-10-06
summary: How should duplicate articles from many sources be handled? Cluster without deleting; code decides mechanical duplicates (T0, T1, T4), the LLM decides same-event and update cases (T2, T3).
summary_vi: Gộp cụm bài trùng nhưng không xoá; code quyết trùng cơ học, LLM quyết trùng ngữ nghĩa, và bài trùng kế thừa kết quả của bài gốc.
---

# PRP-20261001-dedup-architecture — Multi-source duplicate article handling architecture

## Question

- How should the pipeline detect and process articles that several sources publish about the same story, without losing data and without spending tokens on repeated content?
- Who decides each kind of duplicate: deterministic code or the LLM (`article-processor`)?

## Findings

All measurements come from `C:\data\news-scape\monocle.db` (read-only), window 2026-09-28 to 2026-10-01: 1,759 rows in `articles` and 2,074 rows in `seen_articles`. The measuring script lived in a scratchpad outside the repository.

### Operator rulings (2026-10-01, round 2)

- R1. Duplicates MUST NOT be deleted. A confirmed duplicate skips the LLM, inherits the result of its canonical article and stays stored with every source, timestamp and URL.
- R2. Duplication is an investment signal. Frequent republication of one topic indicates attention and sentiment, so clusters are analysis input (see PRP-20261001-insight-analytics).
- R3. Capture everything, process later. Pinned as ADR-0013 and rule 10; item P0 below is its first implementation.

### Existing dedup layers

- SimHash on content (`src/pipeline/change_detect.py:22`) only detects an article changing between two snapshots. It never compares different articles.
- The agent `story-dedup-clusterer` (`.agents/registry.yaml:275`) was designed for the retired Gold lane, is `draft` and never ran.

### The crawl layer drops articles wrongly

- 439 articles were dropped in 3 days (21% of articles seen). They left no Bronze file and no URL to recrawl.

| Class | Articles | Example |
|---|---:|---|
| True duplicate (`ratio >= 85`) | 182 | the same "VPB: Nghị quyết HĐQT…" on cafef RSS and cafef capture |
| Near duplicate (`ratio 60-85`) | 50 | "Đề xuất chuyển tiền quỹ bình ổn xăng dầu…" |
| Wrong drop (`token_set = 100`, `ratio < 60`) | 202 | "Giá vàng 'sập' mạnh sau 1 tháng" matched the baodautu title "1" |
| No fuzzy match | 5 | |

- Root cause 1: `token_set_ratio` returns 100 when the short title's word set sits inside the long one. Short titles match almost anything.
- Root cause 2: the baodautu scraper emits broken titles such as `"1"` and `"2"`. One broken title drops every article containing the digit 1 for the next 48 hours.
- Root cause 3: even at `ratio >= 85`, template titles collide. "GAS: nghị quyết HĐQT số 110 ngày 25/09" matched "MWG: nghị quyết HĐQT số 12 ngày 25/09" at ratio 92.
- Secondary defect: `seen_articles.source_domain` mixes `cafef` and `cafef.vn`, so `exclude_domain` fails to exclude a site compared with itself through two scrapers.

### Duplicates that still reach `articles`

- Method: 5-word shingles, boilerplate shingles (present in more than 2% of articles) removed, containment between two articles.
- Containment >= 0.8 (copy or reprint): 67 of 1,742 redundant clusters, 3.8%.
- Containment >= 0.5 (including same event): 136 of 1,742, 7.8%.
- Same article, different URL: 9 cafef pairs differing only by `?utm_source=du-lieu`, plus same id with a different slug. `url_title_hash` hashes the whole URL.
- Cross-site reprint: AgriS (SBT) vietstock and cafef, containment 1.0, different titles.
- Same event rewritten: PNJ private placement of 550 million shares (baodautu and vietnambiz, 0.78); "HNX chuyển sang HOSE" (vietnambiz and cafef, 0.47).
- Update with new facts: PVcomBank "higher than market price by 60%" became "13,628 VND per share, almost 40% higher". Merging would lose the second article.
- Recurring columns: daily gold price and technical analysis columns share a template but differ in content. They MUST never merge.
- Template false positives: disclosure notices of MBB, MSN, HCM and HDB on cafef reach containment 0.77-0.78 from shared boilerplate.
- SimHash exists on only 138 of 1,759 articles (8%). Most pairs at Hamming distance <= 10 are unrelated; 64-bit SimHash lacks resolution on short Vietnamese news.

### Scaling estimate

- The true duplicate rate is about 15-18% today: 232 true or near duplicates dropped at crawl plus 136 redundant clusters that passed.
- The rate grows with the number of sources covering one event. Disclosures, gold, macro and policy news appear on 3-6 sites at once.
- With 20-30 sources, a 30-50% duplicate rate is realistic. The infrastructure should exist before that scale.

### Capture gaps (ADR-0013)

| Gap | Measurement | Kind |
|---|---|---|
| Fuzzy title filter in `base_scraper` | 439 dropped per 3 days, 202 wrongly | active drop |
| Page 1 only, 6 sections only (baodautu) | store holds about 50% of sitemap articles, daily since 2026-09-20 | scope drop |
| Fixed first page (cafef `PageSize: 20`, tnck `pages_per_cycle: 1`) with the machine off 11-16 hours | cafef backfills 51-103 articles after each long gap, completeness unproven | gap drop |
| Silver dead-letter | 1,461 Bronze files never reach analysis | lost in processing |
| Broken titles (baodautu `"1"`) | article present, wrong metadata | bad data |

## Options

| Option | Benefit | Cost or risk |
|---|---|---|
| A. Pure LLM dedup | Handles semantic cases | Dedup is pairwise: 1,000 articles are 500,000 pairs. Reading all to find duplicates costs about as much as analysing all. T0, T1 and T4 have exact answers. |
| B. Pure code dedup with hard thresholds | 0 tokens | Already failed: 46% wrong drops, GAS merged with MWG. T2 and T3 are semantic. AGENTS.md section 6.C forbids heuristics replacing agent work. |
| C. Hybrid: code clusters mechanical types and nominates candidates, LLM decides semantic types, nothing deleted | Tokens spent only on new information; matches industry practice (MinHash-LSH or SimHash, entity and time blocking, model for the grey zone) | New tables (high-risk schema change) and a contract change for the diff mode |

## Recommendation

Adopt option C, "cluster, never delete". An inverted index on rare shingles suffices at 2,000-5,000 articles per day; no vector DB or embedding service is needed yet.

### Duplicate taxonomy

| Type | Definition | Detection | Decider | Token handling |
|---|---|---|---|---|
| T0 technical copy | same article, other URL or scraper | canonical URL plus SHA256 of normalised paragraphs | code | 0: drop later copy, keep URL as alias |
| T1 reprint | other site republishes near verbatim | containment >= 0.8 and same numbers and same tickers | code | 0: inherit canonical result |
| T2 same event | rewritten, same facts | code nominates: containment 0.3-0.8, or same tickers and numbers, within 48 hours | LLM | analyse the diff only |
| T3 update | same event, new facts | as T2 | LLM | analyse the diff, flag "update" |
| T4 recurring column | same template, other date and content | series key (title template plus date) | code | full analysis; merging across dates is forbidden |

### Pipeline

- A new script `story_cluster.py` (0 tokens) runs after Silver. It applies T0 (`url_canonical` plus `body_sha256`), T4 (`series_key`), a rare-shingle index over a 48-hour window, T1 and T2/T3 nomination.
- Tables `story_clusters` (cluster_id, canonical_id, first_seen_at, last_seen_at, n_members, n_sources) and `cluster_members` (article_id, cluster_id, role, method, score, evidence, decided_by, decided_at). Roles: canonical, alias, copy, candidate, same_event, update, series.
- `article_pack.py` selects by role: canonical, standalone and T4 get a full packet; copies (T0/T1) get no packet; candidates (T2/T3) get a diff packet.
- The conductor stays one `run_code`: phase A runs full batches, phase B runs diff batches with the canonical summary from phase A.
- `--finish` writes inherited results for copies (`l1_source = 'inherited'`, pointing at the canonical). Coverage counts analysed, diff and inherited articles.
- Delivery shows one row per story, a "Sources" column listing every site, and updates on separate rows.

### Diff mode of `article-processor` (contract change)

- Candidate input: canonical summary and theses from phase A, plus the candidate's own paragraphs that share no shingle with the canonical.
- New outputs: `same_event_as` (canonical id, or `null` to split the cluster and queue a full analysis later) and `novelty` (`none | minor | new_facts`).
- Entity recognition and analysis cover only the diff; citations still use the candidate's own paragraph indices. `story-dedup-clusterer` moves to `retired`.

### Merge guards (code, applied to every T1 decision)

- Number guard: the set of numbers in title and lead MUST match. Blocks PVcomBank 60% versus 40%.
- Ticker guard: the ticker set in the title MUST match. Blocks GAS versus MWG.
- Series guard: same `series_key` with a different date MUST NOT merge.
- Boilerplate shingles are removed by per-domain document frequency.
- Broken-title guard: titles under 8 characters or only digits go to dead-letter, not the index.
- The catalogue entity matcher serves only blocking and guards. It never produces recognition output and never counts as analysed.

### Invariant changes (ADR-0016)

- "Every article is fully processed" becomes "every story is fully analysed once; every article gets a full, diff or inherited result with a cluster role".
- Wave coverage stays >= 90% on both layers. The denominator is articles in the wave; the numerator includes inherited and diff articles that pass DoD.
- `l1_source = 'code_first'` stays excluded. `l1_source = 'inherited'` counts, because the canonical result came from a model.

### Roadmap

| Phase | Work | Proof |
|---|---|---|
| P0.1 | Disable crawl fuzzy dedup (`fuzzy_dedup: false` default), keep exact match | two titles at `token_set = 100`, `ratio < 60` are both stored |
| P0.2 | Canonical URL: strip `utm_*`, `fbclid`, `gclid`, fragment; cafef keyed by trailing id | the 9 real cafef pairs map to one `url_canonical` |
| P0.3 | Reject broken baodautu titles to dead-letter | title `"1"` rejected |
| P0.4 | Normalise `source_domain` in `seen_articles` | test |
| P0.5 | `scripts/dedup_audit.py` (read-only), radar line with T0-T4 rates | reproduces the numbers above on the 3-day snapshot |
| P1 | `story_cluster.py` writes clusters, `article_pack` unchanged, 1-2 weeks shadow run | T1 sample of 100 pairs checked by `adversarial-dod-verifier`, wrong merges < 1% |
| P2 | Pack skips copies, `--finish` writes inherited results, delivery groups rows; ledger records "tokens avoided" as information, never as a gate | coverage holds |
| P3 | Diff mode, phase A then phase B in one `run_code`; calibrate on about 200 labelled pairs | operator-reviewed sample |
| P4 | Optional embeddings, only if P3 shows frequent `same_event_as` on pairs code did not nominate | measurement |

- P0 was expected to save about 200 articles per 3 days and raise Article Lane intake by about 10%.

### Capture completeness (ADR-0013)

- A discovery ledger `discovered_urls` (url_canonical, source, first_seen_via, first_seen_at, state, attempts, last_error) is written before any filter. States: discovered, then captured, alias, gone or dead_letter. No "dropped" state exists.
- Watermark pagination: read listings until a page holds only known URLs, with a per-source page cap. After downtime the scraper reads deeper automatically.
- Daily sitemap reconciliation (`scripts/capture_reconcile.py`, 0 tokens) records missing URLs with `first_seen_via = 'reconcile'` and backfills them.
- Radar shows per source per day: sitemap count, captured, missing, backfilled. Missing > 2% is RED.
- Order C1: P0.1-P0.4. Order C2: read-only reconcile for baodautu and cafef, shown on radar. Order C3: the `discovered_urls` table (schema change).
- Order C4: watermark pagination; sections kept only for ordering. Order C5: automatic backfill and clearing the 1,461 Silver dead-letters.

### Expected effect

| Scale | True duplicate rate | Tokens avoided |
|---|---|---|
| Today, 8 sources | 15-18% | P2 about 4% (T0/T1); P3 about 3% more (diff reading saves an estimated 60-70% per article) |
| 20-30 sources | 30-50% | 20-35%, mostly from T1 (disclosures, prices, macro) |

- At current scale the main value of P0-P1 is no lost articles and no wrong merges. Token savings dominate once sources grow.

### Risks

| Risk | Mitigation |
|---|---|
| Wrong merge loses news | Nothing deleted; every decision carries `evidence` and can be split; number and ticker guards; verifier sampling |
| A faulty canonical analysis spreads to the cluster | Choose canonical by content length and source quality, not publish time; if it fails DoD the next member becomes canonical |
| 48-hour window splits a long event | Clusters stay open by `last_seen_at`; a late match joins as candidate |
| Phase B waits on phase A | Phase B holds only short diff articles; a missing canonical promotes the candidate to full analysis |
| P0.1 raises Bronze crawl load by about 20% | Within capacity; T0 is blocked at canonical URL before download |

### Fields kept for the signal

- Every member with `source_domain` and `published_at` gives coverage intensity (articles and sources per topic per day).
- Publication order gives propagation speed (time from the first to the third article, first source).
- Roles `copy` versus `same_event` give the stale-reprint ratio; `update` and `novelty` give story momentum.
- Canonical and diff sentiment separate per-story sentiment (one vote per story) from per-coverage sentiment (one vote per article).
- Inheritance raises coverage: only 27% of articles since 2026-09-01 have a model result (3,120 of 11,591).

## Outcome

- Operator approved on 2026-10-02 as ADR-0013 (capture everything, process later) and ADR-0016 (dedup clusters and insight signal), implemented under US-033.
- Done: capture items C1 to C5, P1 and P2.
- Not done at approval time: P3 (diff mode), P4 (embeddings) and per-cluster row grouping in delivery. Tracked in `docs/OPEN-ITEMS.md` item CAP-1.
- ADR-0015 (exempt disclosure titles from crawl fuzzy dedup) is related; P0.1 removed crawl fuzzy dedup entirely.
- Reconstructed on 2026-10-06: the related link to ADR-0015 and the Options table were added from the original "why not pure LLM / pure code" sections.
