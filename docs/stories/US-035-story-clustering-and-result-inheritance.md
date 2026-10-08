---
id: US-035
type: story
title: Story clustering and result inheritance
status: implemented
lane: high-risk
created: 2026-10-05
updated: 2026-10-06
lang: en
authors: [An Pham Thanh, claude-opus-5-5]
adr: [ADR-0016]
plan: []
evidence:
  - commit:fb9b1c2
  - commit:bfbd5e6
  - path:project/src/pipeline/story_cluster.py
  - path:project/src/pipeline/inherit.py
  - path:project/src/pipeline/cluster_job.py
  - path:project/src/analytics/signals.py
  - path:project/scripts/story_cluster.py
  - path:project/scripts/signal_build.py
  - path:project/src/export/radar_sheet.py
  - path:docs/proposals/20261001-dedup-architecture.md
  - path:docs/proposals/20261001-insight-analytics.md
  - test:project/tests/test_story_cluster.py
  - test:project/tests/test_inherit.py
  - test:project/tests/test_signal_build.py
  - metric:pytest project/tests/test_story_cluster.py 14 of 14 passed, 2026-10-05 (harness.db)
verify: "python -m pytest project/tests/test_story_cluster.py project/tests/test_inherit.py project/tests/test_signal_build.py -q -p no:cacheprovider"
reconstructed: 2026-10-06
summary: Duplicate articles are clustered by story without deletion; exact or 0.95-containment copies skip the model and inherit the canonical result, and derived signal tables measure coverage frequency and breadth.
---

# US-035 — Story clustering and result inheritance

## Contract

Duplicate articles are grouped into story clusters and never deleted. A near-verbatim copy skips the model and inherits the canonical article's result, marked `l1_source = 'inherited'`. Rewrites and same-event articles still get full analysis, and coverage signals count every copy.

## Acceptance Criteria

- [x] P1: `story_cluster.py` writes clusters deterministically, without changing or deleting any article.
- [x] P2: a `copy` (exact body, or containment of at least 0.95 with the same figures and tickers) inherits the canonical result through `inherit.py`.
- [x] Inherited rows count as analysed; `l1_source = 'code_first'` stays excluded from every count.
- [x] I1, I2 and I4: `signal_build.py` fills the derived signal tables, and delivery carries the "Radar chú ý" sheet.
- [x] Tests cover clustering, inheritance and signals without touching the operational DB.
- [ ] P3 divergence mode, P4 embeddings, I3 price data and I5 promotional flag. Open in `docs/OPEN-ITEMS.md` CAP-1, each needing its own decision.

## Design Notes

- Implements ADR-0016, which amends the "every article is fully processed" invariant of ADR-0010.
- Join a copy to its best neighbour only. Transitive union on a shared ticker once chained 10 PNJ events into one cluster.
- Require at least 40 shingles before trusting containment; boilerplate-only articles gave a false containment of 1.0.
- Titles carrying different dates never merge, so recurring dated columns stay apart.
- A copy waits up to 48 hours (`HOLD_HOURS`) for its canonical result, then returns to the article selector.
- The crawl-time fuzzy title dedup tests were removed in favour of story clusters.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python -m pytest project/tests/test_story_cluster.py -q` | 14 of 14 passed (harness.db, 2026-10-05) |
| Integration | combined capture and clustering verify run | 87 passed (harness.db row US-033, 2026-10-02) |
| Platform | morninger runs clustering and signals after derive | deployed; no measured wave recorded here |

## Evidence

- Commit fb9b1c2: `story_cluster.py`, `cluster_job.py`, `signals.py`, `signal_build.py`, `radar_sheet.py`, delivery changes, ADR-0016 and tests.
- Commit bfbd5e6 (commit labelled US-033): `src/pipeline/inherit.py` and `test_inherit.py` landed with the capture work.
- `harness.db` row US-035 records "Cum hoa tin tuc va tin hieu insight" with the story_cluster verify command.
- This file was renamed from a duplicate Bronze story file of 2026-10-05; that content now lives only in US-036.
