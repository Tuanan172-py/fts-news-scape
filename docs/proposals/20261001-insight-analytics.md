---
id: PRP-20261001-insight-analytics
type: proposal
title: Insight analytics from news data
status: decided
lane: high-risk
created: 2026-10-01
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
adr: [ADR-0016, ADR-0013]
story: [US-033]
plan: []
related: [PRP-20261001-dedup-architecture]
evidence:
  - commit:579163c
  - metric:11,591 articles since 2026-09-01; 3,873 with entity recognition; 3,120 with content analysis
  - "metric:attention z-score window 2026-09-25 to 2026-09-29 versus baseline from 2026-09-02"
  - metric:source sentiment skew measured on 2,553 analysed articles across 6 sources
  - metric:23% of entity-tagged articles published before 09:00, 30% after 15:00
original: "commit:579163c"
reconstructed: 2026-10-06
summary: Which insights can be derived from existing news data? Build deterministic derived signal tables (attention, stale reprints, adjusted sentiment, topics, links, timing), and validate them against prices before calling them trading signals.
summary_vi: Dựng bảng chỉ số phái sinh tất định (chú ý, tin đăng lại, sentiment hiệu chỉnh, chủ đề, liên kết, thời điểm) và chỉ gọi là tín hiệu sau khi kiểm chứng với giá.
---

# PRP-20261001-insight-analytics — Insight analytics from news data

## Question

- Which investor insights can be derived from the news data already stored, and what must be true before any of them is presented as a trading signal?

## Findings

Viewpoint: a data analyst exploring the existing data. Illustrative numbers come from the operational DB (read-only): 11,591 articles since 2026-09-01, of which 3,873 have entity recognition and 3,120 have content analysis. None of the illustrative numbers was validated against price or volume.

### Data available

| Field | Source | Coverage |
|---|---|---|
| title, body, source, publish time | `articles` | all |
| entities: ticker, GICS3 industry, index, macro, asset class | `l1_outputs` (model) | about 33% |
| summary, theses, implications, `sentiment`, `time_sensitivity`, citations | `agent_outputs` (model) | about 27% |
| duplicate cluster and role | not yet (dedup P1) | |
| price and volume | not yet | |

- Counting, aggregation and statistical normalisation over existing results is mechanical work for scripts at 0 tokens (AGENTS.md section 6.C).
- Any new semantic field, such as a promotional flag, MUST come from `article-processor` and is a high-risk contract change.

### Measured illustrations

- Abnormal attention, 2026-09-25 to 2026-09-29 versus baseline from 2026-09-02:

| Ticker | z | Recent articles per day | Baseline | Sources | Sentiment |
|---|---:|---:|---:|---:|---|
| KOS | 7.5 | 4.0 | 0.2 | 4 | 9 negative, 3 neutral |
| PVT | 6.6 | 7.3 | 0.5 | 8 | 6 positive, 9 negative |
| NT2 | 4.5 | 2.3 | 0.1 | 5 | 5 positive |
| VGC | 4.5 | 2.7 | 0.2 | 5 | 6 positive |
| GMD | 3.4 | 3.7 | 0.5 | 6 | 6 positive, 1 negative |

- KOS shows a sharp attention rise across many sources with dominant negative tone, the alert type users need at the start of the day.
- Weekend volume drops to about 190 articles per day versus about 500 on weekdays, so baselines MUST be normalised by weekday.
- Source tone skew:

| Source | Articles | Positive | Negative |
|---|---:|---:|---:|
| baodautu.vn | 297 | 66% | 14% |
| fireant.vn | 65 | 63% | 8% |
| thoibaotaichinhvietnam.vn | 188 | 54% | 14% |
| vneconomy.vn | 432 | 52% | 16% |
| cafef.vn | 1,223 | 42% | 21% |
| vietstock.vn | 348 | 40% | 27% |

- A "positive" baodautu article carries less information than a "positive" vietstock article. Adding a positive-toned source inflates raw sentiment.
- Publication timing on 3,873 entity-tagged articles: 23% before market open (09:00) and 30% after 15:00, when HOSE has closed at 14:45. About 53% arrive outside trading hours.

### Six directions

- H1 abnormal attention. Metrics: `ama_z` (daily z-score per ticker against a 20-day weekday-normalised baseline), `breadth` (distinct sources), `share` (ticker share of daily articles, stable when sources are added), `silence` (watchlist ticker without articles for N days). Basis: Da, Engelberg and Gao (2011); Barber and Odean (2008); Fang and Peress (2009).
- H2 stale reprints and propagation, needing dedup clusters. Metrics: `stale_ratio`, `cascade_minutes` (first to third article), `n_updates`, `first_source`. Basis: Tetlock (2011). This is the technical reason duplicates MUST NOT be deleted.
- H3 adjusted sentiment. Metrics: `net_sent_story` (one vote per story), `net_sent_volume` (one vote per article), their gap (amplification), `net_sent_norm` (source baseline removed), `dispersion` (PVT: 6 positive, 9 negative in 3 days), `sent_shift`. Basis: Tetlock (2007).
- H4 emerging topics. Use model entity codes (`IND_GICS3:*`, `MACRO*`, `ASSET_CLASS:*`) as topics, daily share, burst detection, weekly industry heat map. No new LLM field. Basis: Shiller (2019); Kleinberg (2002).
- H5 entity link network. Co-mention graph over 30 days weighted by PMI; track centrality change and new edges. Basis: Scherbina and Schlusche; Hoberg and Phillips (2016).
- H6 timing and source. Map each article to the first session it can affect (after 14:45 counts for the next session). Measure lag from official disclosure to press and a source reliability score (lead rate, original rate, tone skew).

## Options

| Option | Benefit | Cost or risk |
|---|---|---|
| A. Present raw counts and raw sentiment to users now | No new work | Inflated by new sources, source tone skew and reprints; misleading as a signal |
| B. Deterministic derived signal tables (H1-H6), labelled "attention" and "press tone" until validated | 0 tokens, rebuildable, honest labelling | New tables and a new delivery sheet (high-risk) |
| C. B plus price event study (H7) before calling anything a trading signal | Turns descriptions into tested signals | Needs a daily OHLCV source with verified terms of use |

## Recommendation

Adopt B now and C as the validation gate.

- All metrics are rebuildable derived tables, droppable and rebuilt from `articles`, `l1_outputs`, `agent_outputs` and `cluster_members` (rule 10 section 2.6).
- `scripts/signal_build.py` (0 tokens, deterministic, runs after `--finish`) writes three tables.
  - `signal_daily`: entity_id, trade_date, n_articles, n_sources, n_stories, share, ama_z, stale_ratio, cascade_minutes, n_updates.
  - `signal_daily` also holds net_sent_story, net_sent_volume, net_sent_norm, dispersion, sent_shift, first_source, coverage_pct.
  - `entity_links`: entity_a, entity_b, window_end, n_co, pmi. `source_profile`: source, window_end, pos_rate, neg_rate, lead_rate, original_rate.
- Outputs: a radar and ops console line "abnormal attention today", and a "Radar chú ý" sheet per user watchlist in `write_user_output.py`.
- H7 validation: first test whether today's `ama_z` predicts abnormal volume in the next session, the most stable relation in the literature. Then test abnormal returns against `net_sent_norm`, `stale_ratio` and `dispersion`.
- Without H7, reports MUST present these numbers only as "attention level" and "press tone", never as trading signals.

### Bias controls

| Bias | Control |
|---|---|
| New sources inflate counts | use `share` and per-source z-scores, not absolute counts |
| Only about 27-33% of articles have model results | report coverage with every metric; dedup P2 inheritance raises coverage; code-first output MUST NOT be input |
| Capture gaps (baodautu about 50%) | fix per ADR-0013 before trusting attention metrics |
| Promotional and real-estate PR inflate positive tone | model-generated `is_promotional` flag (high-risk contract change) |
| Holidays and weekends | weekday baselines; map articles to the next trading session |
| Broken titles cause wrong merges | broken-title guard (dedup P0.3) |

### Roadmap

| Phase | Work | Depends on | Lane |
|---|---|---|---|
| I1 | `signal_build.py` for H1, H3 (non-cluster part), H4, H6; sheet "Radar chú ý" | existing data | high-risk (new tables, delivery change) |
| I2 | H2 and `net_sent_story` | dedup P1 cluster tables | normal |
| I3 | OHLCV table and H7 event study for `ama_z` against volume | price source, terms verified | high-risk |
| I4 | H5 link network, `source_profile` | I1 | normal |
| I5 | `is_promotional` flag; extract broker recommendations (titles such as `TCBS:`, `VCBS:`) | change to `agent-output-v2-lean` | high-risk |

- Priority: ADR-0013 C1-C2 (complete capture), then dedup P1, then I1, then I3. Attention built on data missing 50% of one source mismeasures coverage breadth.

### References

- Barber and Odean (2008), Review of Financial Studies. Da, Engelberg and Gao (2011), Journal of Finance. Fang and Peress (2009), Journal of Finance.
- Tetlock (2007), Journal of Finance. Tetlock (2011), Review of Financial Studies. Kleinberg (2002), KDD. Shiller (2019), Princeton University Press.
- Hoberg and Phillips (2016), Journal of Political Economy. Scherbina and Schlusche, working paper on news-implied linkages.

## Outcome

- Operator approved on 2026-10-02 under ADR-0016, with capture prerequisites in ADR-0013, implemented by US-033.
- Done: I1, I2 (except `cascade_minutes`, because clusters were still sparse), I4 and the "Radar chú ý" sheet.
- Not done at approval time: I3 (needs price data) and I5 (model contract change).
- Reconstructed on 2026-10-06: the Options table was derived from the original sections 3 and 4; no new findings were added.
