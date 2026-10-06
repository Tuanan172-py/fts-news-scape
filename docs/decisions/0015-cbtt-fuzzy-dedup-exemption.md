---
id: ADR-0015
type: adr
title: Exempt CBTT disclosure titles from crawl-layer fuzzy dedup
status: rejected
lane: normal
created: 2026-09-24
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
approvers: []
related: [ADR-0013]
evidence:
  - commit:dd1e709
  - commit:579163c
  - commit:bfbd5e6
  - path:plans/20260924-1627-codebase-audit-cleanup-modularization/plan.md
  - path:plans/20260924-1627-codebase-audit-cleanup-modularization/reports/R2-architecture-critique.md
  - path:docs/proposals/research-council-2026-09-24.md
  - path:docs/proposals/dedup-architecture-2026-10-01.md
  - 'metric:about 1,566 hashes in seen_articles with no row in articles, including CBTT titles such as "VHM: CBTT...", research council finding L1, 2026-09-24'
original: "commit:dd1e709"
reconstructed: 2026-10-06
summary: Reserved number for exempting CBTT disclosure titles from crawl-layer fuzzy title dedup; never written and rejected as absorbed, because ADR-0013 removed fuzzy dedup from crawlers entirely.
summary_vi: Số ADR dành cho việc miễn lọc trùng mờ cho tiêu đề CBTT; không được viết và bị bác vì ADR-0013 đã gỡ hẳn lọc mờ ở tầng cào.
---

# ADR-0015 — Exempt CBTT disclosure titles from crawl-layer fuzzy dedup

This whole record is reconstructed on 2026-10-06 from the sources in `evidence`. No ADR-0015 text existed before; the number was only reserved.

## Context

- The research council of 2026-09-24 found that crawl-layer fuzzy dedup dropped articles, even comparing a source against itself (finding L1, reconstructed from `docs/proposals/research-council-2026-09-24.md`).
  - `src/core/base_scraper.py` passed `self.name` ("cafef") while `seen_articles.source_domain` also held "cafef.vn". The `!=` filter in `dedup.py` therefore failed to exclude the same source.
  - `token_set_ratio` returns 100 when one title is a subset of another.
  - About 1,566 hashes existed in `seen_articles` with no row in `articles`, including disclosure titles such as "VHM: CBTT…". No Bronze was stored, so they could not be recovered.
- The R2 architecture critique split the fix in two (reconstructed from `reports/R2-architecture-critique.md` §2.1 and §2.3):
  - Passing the correct `source_domain` restores the "different source" design and is lane normal.
  - Exempting a whole class of titles (CBTT) from fuzzy matching relaxes the dedup guarantee and needed its own ADR, numbered 0015.
- The audit plan of 2026-09-24 reserved ADR-0015 "Chính sách fuzzy dedup cho tin CBTT" for sprint S1, item C3 (reconstructed from `plans/20260924-1627-codebase-audit-cleanup-modularization/plan.md` §3 and §6).

## Decision

- D1. Rejected; never drafted. The proposed exemption would have kept CBTT disclosure titles out of crawl-layer fuzzy title dedup, and would have kept duplicates in Bronze with `duplicate_of` (R2 §2.3 scope).
- D2. The need disappeared on 2026-10-01. ADR-0013 made capture an unfiltered layer and removed the `fuzzy_dedup` setting from crawlers, so no title class needs an exemption.
- D3. The number 0015 MUST stay reserved for this record and MUST NOT be reused.

## Alternatives

| Option | Why rejected |
|---|---|
| Write ADR-0015 as planned and exempt CBTT titles only | Fixes one loss class and leaves the 46% wrong drops on other titles measured on 2026-10-01 (ADR-0013 context). |
| Fix only `source_domain` (lane normal) and keep fuzzy dedup | Restores the intended design but still drops cross-source titles before Bronze, which loses the frequency signal (ADR-0013). |
| Remove fuzzy dedup from crawlers entirely | Chosen, through ADR-0013 and rule 10; implemented in commit bfbd5e6 (US-033). |

## Consequences

- No CBTT-specific rule exists. CBTT titles are captured like every other article under ADR-0013.
- The roughly 1,566 articles already dropped before Bronze stay lost unless sitemap reconciliation finds them again.
- Duplicate handling moved after Bronze: clustering and inherited results under ADR-0016.

### Current status (2026-10-06)

- Rejected as absorbed by ADR-0013. Fuzzy dedup was removed from `base_scraper` in commit bfbd5e6.

## Rollback

- Not applicable: nothing was implemented under this number. Restoring crawl-layer fuzzy dedup would require reversing ADR-0013 through a new ADR.

## Follow-up

- [x] Remove crawl-layer fuzzy dedup (ADR-0013, commit bfbd5e6).
- [ ] Optionally measure how many of the 1,566 dropped hashes `capture_reconcile.py` recovered from sitemaps; no measurement is recorded.
