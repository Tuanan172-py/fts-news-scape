---
id: ADR-0019
type: adr
title: Exclude thin articles from Article Lane packets
status: accepted
lane: normal
created: 2026-10-05
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
approvers: [operator 2026-10-05]
story: [US-037]
amends: [ADR-0010]
related: [ADR-0013, ADR-0016, ADR-0017, ADR-0018]
evidence:
  - commit:0340f64
  - commit:737d8ce
  - path:project/scripts/article_pack.py
  - path:project/src/agent/article_contract.py
  - path:project/scripts/pipeline_radar.py
  - test:project/tests/test_article_pack_thin.py
  - metric:202 of 700 articles in 3 Article Lane waves had packet paragraphs totalling 102-494 characters and all failed the Gold gate (session 2026-10-05)
  - metric:MIN_CITATION_CHARS = 20 in article_contract.py, asserted equal in article_pack and article_expand
  - operator:'chose "Loại khỏi packet", 2026-10-05'
original: "commit:737d8ce"
reconstructed: 2026-10-06
summary: Articles whose packet paragraphs contain fewer than two paragraphs of MIN_CITATION_CHARS are thin; load_candidates excludes them by default, radar counts them separately, and one threshold lives in article_contract.py.
summary_vi: Bài không đủ hai đoạn đạt độ dài trích dẫn là bài mỏng, bị loại khỏi packet và đếm riêng trên radar; ngưỡng trích dẫn chỉ nằm một nơi.
---

# ADR-0019 — Exclude thin articles from Article Lane packets

## Context

Measured in the session of 2026-10-05 on 3 Article Lane waves of 700 articles:

- 202 articles had packet paragraphs totalling 102 to 494 characters. All of them failed the Gold gate for lack of long-enough citations.
- Three citation-length thresholds lived in three places with no consistency check.
- The radar count "chờ phân tích" included thin articles, although the next wave could not take them.

Thin articles therefore spent identification tokens, then failed deterministically at `--finish` and held back the rest of their wave. The ADR text names story US-036 and says it shipped with E1 dedupe and the wave-global gate. The `is_thin` and `exclude_thin` code landed in commit 0340f64 labelled US-036. The ADR file and the thin tests landed in commit 737d8ce labelled US-037.

## Decision

### D1. Definition of a thin article

An article is thin when the paragraph array that packing would send to the model has fewer than two paragraphs reaching `MIN_CITATION_CHARS`. It is measured at pack time by `is_thin`.

### D2. Exclude from packets, count separately

- `load_candidates(..., exclude_thin=True)` is the default and excludes thin articles. Every caller sees the same number.
- Radar prints a separate line "Bài mỏng chờ Silver" and MUST NOT merge it into "chờ phân tích".
- Fail-open: when the content cannot be read, the article is kept, and the packing round excludes it later as before.
- A thin article is taken again when its Silver package arrives, or through the refresh repair path the text attributes to ADR 0016.

### D3. One threshold

The canonical `MIN_CITATION_CHARS` lives in `src/agent/article_contract.py`. A test pins the three places to the same value.

## Alternatives

| Option | Why rejected |
|---|---|
| Run only L1 for thin articles | Still spends identification tokens without adding Gold coverage. |
| Keep them and only warn | The backlog keeps entering waves, fails the finish gate and holds the whole wave. |

## Consequences

- Gold tokens are no longer burned on articles that fail deterministically.
- No DB schema change and no output contract change; only the set of articles entering a packet changes.
- Thin articles wait in the radar line until Silver supplies a full body.

### Current status (2026-10-06)

- `is_thin`, `is_thin_row` and `load_candidates(exclude_thin=True)` are in `project/scripts/article_pack.py`.
- `MIN_CITATION_CHARS = 20` is in `article_contract.py`. `test_article_pack_thin.py` asserts that `article_pack`, `article_expand` and `article_contract` agree.
- `pipeline_radar.py` prints the line "Bài mỏng chờ Silver".
- The refresh repair path that re-packs from Silver is defined in ADR-0018.D3. The reference to ADR 0016 in D2 appears to mean ADR-0018; the text is kept as written.

## Rollback

- Re-enable thin articles by passing `exclude_thin=False` at each call site.
- Or run `git revert` on the implementing commit (0340f64, labelled US-036 in the original text).
- No data migration is needed.

## Follow-up

- [ ] Measure how many thin articles recover after Silver arrives, using the radar line "Bài mỏng chờ Silver".
- [ ] Confirm whether the D2 reference to ADR 0016 should read ADR-0018, and record the answer in a later ADR.
- [ ] Resolve the US-036 and US-037 story labels under the ADR-0021 story cleanup (G4).
