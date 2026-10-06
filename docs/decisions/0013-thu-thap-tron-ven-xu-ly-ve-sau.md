---
id: ADR-0013
type: adr
title: Capture everything, process later
status: accepted
lane: high-risk
created: 2026-10-01
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
approvers: [operator 2026-10-01]
story: [US-033, US-036]
related: [ADR-0015, ADR-0012, ADR-0016]
evidence:
  - commit:579163c
  - commit:bfbd5e6
  - path:.agents/rules/10-thu-thap-tron-ven.md
  - path:docs/proposals/dedup-architecture-2026-10-01.md
  - path:docs/proposals/insight-analytics-2026-10-01.md
  - path:project/scripts/capture_reconcile.py
  - test:project/tests/test_capture_registry.py
  - test:project/tests/test_capture_reconcile.py
  - metric:439 articles dropped by title similarity in 3 days, 202 (46%) wrongly, operational DB read-only 2026-10-01
  - metric:baodautu store held about 50% of sitemap articles 2026-09-20 to 2026-10-01; 2026-09-30 sitemap 101 versus store 57
  - metric:1,461 Bronze files in Silver dead-letter, 2026-10-01
  - operator:pinned 2026-10-01 ("lấy về tất cả, không bỏ sót; loại trùng, làm sạch là bước xử lý về sau; raw có bao nhiêu tin cần lấy về tất cả; thiết kế kiến trúc cần đảm bảo yêu cầu không bỏ sót")
original: "commit:579163c"
reconstructed: 2026-10-06
summary: Capture is an unfiltered layer; every discovered URL enters a discovery ledger, crawlers paginate by watermark and backfill, sitemaps reconcile daily, duplicates are kept and clustered, and a capture-coverage gap above 2% per day is red.
summary_vi: Thu thập không lọc, mọi URL vào sổ phát hiện, phân trang theo watermark, đối chiếu sitemap hằng ngày, bài trùng được giữ và cụm hoá.
---

# ADR-0013 — Capture everything, process later

## Context

The operator pinned the principle on 2026-10-01:

> "lấy về tất cả, không bỏ sót; loại trùng, làm sạch là bước xử lý về sau; raw có bao nhiêu tin cần lấy về tất cả; thiết kế kiến trúc cần đảm bảo yêu cầu không bỏ sót"

Measurements on 2026-10-01 (operational DB, read-only):

- `base_scraper` dropped articles by title similarity before saving: 439 articles in 3 days, 202 of them (46%) wrongly. No Bronze and no URL remained.
- Against the official baodautu sitemap from 2026-09-20 to 2026-10-01, the store held only about 50% of articles. On 2026-09-30 the sitemap had 101 articles and the store 57. Cause: only page 1 of 6 sections was crawled.
- Under ADR-0012, everything stops while the machine is off. The cafef crawler had gaps of 11 to 16 hours and read only the first page (`PageSize: 20`).
- 1,461 Bronze files sat in the Silver dead-letter: raw existed, but content never reached analysis.

The frequency and breadth of coverage of a topic is itself an investment signal. Dropping duplicates at the crawl layer destroys that signal. This ADR also absorbed the reserved ADR-0015 (CBTT fuzzy-dedup exemption), because removing fuzzy dedup made the exemption moot.

## Decision

- D1. Capture is an unfiltered layer. All selection happens after Bronze and MUST NOT delete articles.
- D2. Add a discovery ledger (`discovered_urls`). Every URL seen MUST be recorded before any filtering, with a status lifecycle. No status means "dropped".
- D3. Crawlers paginate by watermark and backfill automatically after the machine was off.
- D4. Independent reconciliation runs daily against each source's sitemap or by-date API. Missing articles are crawled again.
- D5. Duplicates are kept and clustered. A duplicate MAY skip the LLM by inheriting the result of its original, and it MUST still count in frequency metrics.
- D6. Radar shows a capture-coverage metric. A gap above 2% in one day is red.
- D7. The principle is accepted now. Code and schema changes that enforce it follow a separate story. The enforcing rule is `.agents/rules/10-thu-thap-tron-ven.md`.

## Alternatives

| Option | Why rejected |
|---|---|
| Keep fuzzy filtering at the crawl layer with a higher threshold | Still drops articles without a trace, and still loses the frequency signal. |
| Crawl only finance sections | Macro, policy and company news is spread across many sections. Classification belongs to the processing step. |
| Exempt only CBTT disclosure titles from fuzzy dedup (reserved ADR-0015) | Fixes one class of loss and leaves the rest; removing fuzzy dedup from crawlers covers it (reconstructed from `plans/20260924-1627-codebase-audit-cleanup-modularization/plan.md` §6 and ADR-0015). |

## Consequences

- Crawl load rises: about 20% from dropping fuzzy filtering, plus sitemap backfill (baodautu doubles). Acceptable under the current `rate_limit`.
- More articles enter Article Lane. Tokens do not rise in proportion thanks to duplicate clustering (dedup proposal P2).
- The `fuzzy_dedup` setting is removed from crawlers. Section parameters only set crawl order, not scope.

### Current status (2026-10-06)

- Enforced. US-033 removed fuzzy dedup from `base_scraper`, added the URL registry, watermark pagination and `capture_reconcile.py` (commit bfbd5e6).
- ADR-0016 implements duplicate clustering and inherited results. Rule 10 now lists sources without a usable sitemap (vietstock, vietnambiz, thoibaotaichinhvietnam).
- Later findings recorded in rule 10: cafef lacked 64% and tnck 68% against sitemaps. Rule 10 also lists 2,045 articles missing raw files. US-036 later traced missing raw files to Bronze written under the wrong root and relocated 2,750 files.

## Rollback

- Rule 10 and this ADR are the contract; reverting them requires a new ADR approved by the operator.
- Code changes of US-033 revert per commit (bfbd5e6). Restoring `fuzzy_dedup` in `base_scraper` returns the old filtering, at the measured cost of silent loss.

## Follow-up

- [x] Discovery ledger, watermark pagination, sitemap reconciliation (US-033, commit bfbd5e6).
- [x] Duplicate clustering with inherited LLM results (ADR-0016).
- [ ] Reconciliation channel for sources without a usable sitemap (rule 10 §3.1).
- [ ] US-036: restart `morninger` so relocated Bronze is derived into Silver.
