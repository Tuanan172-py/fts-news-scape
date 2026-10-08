---
id: US-033
type: story
title: Capture reconcile, sitemap reconciliation and watermark pagination
status: implemented
lane: high-risk
created: 2026-10-02
updated: 2026-10-06
lang: en
authors: [An Pham Thanh, claude-opus-5-5]
adr: [ADR-0013]
plan: []
evidence:
  - commit:bfbd5e6
  - path:project/src/db/registry.py
  - path:project/src/core/pagination.py
  - path:project/src/core/urlnorm.py
  - path:project/src/pipeline/reconcile.py
  - path:project/src/pipeline/backfill.py
  - path:project/scripts/capture_reconcile.py
  - path:.agents/rules/10-thu-thap-tron-ven.md
  - path:docs/proposals/20261001-dedup-architecture.md
  - test:project/tests/test_capture_registry.py
  - test:project/tests/test_capture_reconcile.py
  - test:project/tests/test_capture_backfill.py
  - metric:87 tests passed for the combined capture and clustering verify command, 2026-10-02 (harness.db)
verify: "python -m pytest project/tests/test_capture_registry.py project/tests/test_capture_reconcile.py project/tests/test_capture_backfill.py -q -p no:cacheprovider"
reconstructed: 2026-10-06
summary: Crawlers record every discovered URL in a discovery ledger before any filter, paginate by watermark until a page holds only known articles, and a daily sitemap reconciliation backfills missing articles.
---

# US-033 — Capture reconcile, sitemap reconciliation and watermark pagination

## Contract

The capture layer drops no article. Every URL seen in a listing, RSS feed, API or sitemap is recorded before any filter. Crawlers read past page one after downtime, and a daily sitemap check backfills whatever the store is missing.

## Acceptance Criteria

- [x] C1: crawl-time fuzzy title dedup is off, URLs are canonicalised (`urlnorm.py`), broken titles go to dead-letter, and `source_domain` is normalised.
- [x] C2: `capture_reconcile.py status` reports sitemap count, captured, missing and backfilled per source per day.
- [x] C3: table `discovered_urls` holds every discovered URL with states `discovered`, `captured`, `gone` or `dead_letter`; URL variants go to `url_aliases`.
- [x] C4: `paginate_until_known` reads listings until a page holds only known URLs, with a per-source page cap of 8 by default.
- [x] C5: `capture_reconcile.py run` backfills missing URLs and `recapture` restores lost Bronze; morninger runs the reconcile after each capture cycle.
- [x] Each step has tests and no test uses the operational DB.
- [ ] Missing share against the sitemap stays under 2% per source per day. Still red at the audit of 2026-10-05 (see US-037).

## Design Notes

- Implements ADR-0013 and rule 10; capture items C1 to C5 come from the capture section of the dedup architecture proposal.
- `harness.db` row US-033 originally covered capture, clustering and insight signals together. The operator's delegate split clustering and inheritance out to US-035 on 2026-10-06.
- Sources without a usable sitemap (vietstock, vietnambiz, thoibaotaichinhvietnam) are reported on the radar as lacking a reconciliation channel.
- `RawStore` path and overwrite fixes shipped in the same commit but belong to US-036.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `verify` command in frontmatter | passed within the 87-test run of 2026-10-02 (harness.db) |
| Integration | `python scripts/capture_reconcile.py status` | coverage table per source and day |
| Platform | missing share under 2% per day | red on 2026-10-05: baodautu 66%, cafef 61%, tinnhanhchungkhoan 61% missing |

## Evidence

- Commit bfbd5e6: discovery ledger, URL normalisation, pagination, reconcile, backfill, morninger hook, scraper changes and tests.
- The same commit added `src/pipeline/inherit.py` and `test_inherit.py`; they are recorded in US-035, which owns clustering and inheritance.
- Platform figures come from the orchestration audit `docs/proposals/20261005-audit-dieu-phoi-agent.md`, finding F7.
