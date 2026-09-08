# Plan — Market news-source expansion (Web Monocle)

Created 2026-09-07 · Owner: producer/dev · Code root: `project/` (NOT repo root)

## Goal

Broaden market coverage with high-quality niche VN sources, strictly inside the existing
Bronze framework: **RawStore.save (byte-exact WORM) BEFORE any parse → `.meta.json` →
Silver derive → change detection**. Headline asks: **TNCK** + **Đầu Tư**. Deep-research
adds: **vietnambiz**, **TBTC**, **NSO** (gated).

## Authoritative inputs

- `research/researcher-03-live-verification-report.md` — **AUTHORITATIVE** (curl-verified 2026-09-07). Wins over 01/02 and repo docs.
- `scout/scout-01-touchpoints-report.md` — file touchpoint checklist per source.
- `research/researcher-01-*` (TNCK API JSON fields) · `research/researcher-02-*` (NSO URL patterns).

## Core decisions (locked — do not re-litigate)

1. **New generic `rss_capture` scraper** (`method: rss_capture` → `REGISTRY["_rss_capture"]`).
   Collapses the vneconomy/vietstock copy-paste pattern into one config-driven class.
   Makes vietnambiz + TBTC **YAML-only** and Bronze-compliant. Written once in phase-01.
2. **Generic `method: rss` is NOT Bronze-compliant** — `RSSScraper` never calls RawStore.
   Evidence: only cafef/vietstock/vneconomy have `data/raw_html/` dirs, and those are
   exactly the only 3 enabled domains. Enabled ≡ capture. New sources must capture.
3. **TNCK**: no RSS (302/13-byte). JSON zone API only. Upgrade `tnck.py` to `CaptureMixin`,
   expand 1 → 9 zones. `source_domain` = **`tinnhanhchungkhoan.vn`** (non-www).
4. **baodautu**: RSS permanently broken (server emits empty "Trang chủ" channel). Becomes a
   bespoke HTML listing scraper. Close out the dead "re-enable when feed has items" comment.
5. **NSO**: network-blocked (TCP RST from 2 egress paths). No scraper. Gated phase, first
   step = prove connectivity from the deployment host.

## Phases

| # | Phase | Status | Progress | Description |
|---|-------|--------|----------|-------------|
| 01 | [rss-capture framework + vietnambiz](phase-01-rss-capture-framework-vietnambiz.md) | 🔲 Not started | 0/9 | Build generic `rss_capture` class; re-enable vietnambiz with 6 live feeds (3 new) under Bronze capture; truth-sync the stale domain matrix. |
| 02 | [TBTC (thoibaotaichinhvietnam)](phase-02-tbtc-new-source.md) | 🔲 Not started | 0/8 | New source, YAML-only on top of phase-01. 9 RSS feeds, clean ISO `+07:00`, strong đầu tư công coverage. |
| 03 | [TNCK capture upgrade](phase-03-tnck-capture-upgrade.md) | 🔲 Not started | 0/10 | Add `CaptureMixin` to `tnck.py`, expand zones, fix the `.vn`-suffix host-resolution hack, ship `domains/tnck/schema.yaml`. |
| 04 | [baodautu HTML listing](phase-04-baodautu-html-listing.md) | 🔲 Not started | 0/11 | Bespoke listing scraper `…-d<N>/p<page>`, body `#content_detail_news`, bespoke `dd/MM/yyyy HH:mm` date parse. Hardest phase. |
| 05 | [NSO — gated / deferred](phase-05-nso-gated-deferred.md) | 🔲 Not started | 0/5 | Connectivity gate from deployment host. If blocked: close as WONTFIX, use TBTC/baodautu as KTXH proxies. No scraper is written in this plan. |

Legend: 🔲 Not started · 🟡 In progress · ✅ Done · ⛔ Blocked

## Sequencing rationale

Given order = effort/value ascending. Front-loading vietnambiz+TBTC de-risks the framework
(`rss_capture`) on the two cheapest sources **before** the headline asks (TNCK, baodautu)
depend on nothing but their own code. TNCK and baodautu are neither dropped nor diluted —
they get the two largest phases. Phases 01→02 are strictly sequential (02 needs 01's class).
03 and 04 are independent of 01/02 and of each other; they may run in parallel.

## Global non-negotiables (every phase)

- `RawStore.save()` is the **first** action after fetch, before any parse. Raw `.html` never mutated.
- `compliance.respect_robots: true` · `rate_limit: >= 3.0`
- `published_at` ISO 8601 with `+07:00` · `metadata["language"]` set
- `detail.max_details_per_cycle` cap honoured in `enrich()`
- **No `raise`** — every error → `self.errors.append(...)`; `BaseScraper.run()` must never crash
- New scraper module imported in `src/scrapers/__init__.py`; unit test with `FakeHTTP`, zero network

## Global acceptance (run after the last phase in scope)

```
pytest -q                                     # all green
python scripts/diagnose_sources.py            # every enabled domain parses
python scripts/run_once.py                    # Bronze capture + Silver re-derive
python scripts/report_drift.py                # no new TEMPLATE_DRIFT / SELECTOR_BROKEN
```

Open questions are carried per-phase; researcher-03 §Unresolved items 3–7 are assigned to
phases 03, 04 and 05.
