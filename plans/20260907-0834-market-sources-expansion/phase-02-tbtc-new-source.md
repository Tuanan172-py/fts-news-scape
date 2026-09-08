# Phase 02 — Thời báo Tài chính Việt Nam (TBTC) — new source

## Context links

- Parent plan: [plan.md](plan.md)
- **Depends on: [phase-01](phase-01-rss-capture-framework-vietnambiz.md)** (`RssCaptureScraper` must exist)
- Research: [researcher-03 §4](research/researcher-03-live-verification-report.md) (all selectors/feeds curl-verified) · [scout-01](scout/scout-01-touchpoints-report.md)
- Repo docs: `project/docs/dev/03-adding-a-source.md` · `project/docs/design/06-raw-html-capture.md` · `project/docs/design/12-bronze-to-silver-rules.md`

## Overview

| | |
|---|---|
| Date | 2026-09-07 |
| Description | Onboard `thoibaotaichinhvietnam.vn` as a brand-new source: **zero new Python**, one YAML on `method: rss_capture` + tests + fixtures + docs. Ministry-of-Finance-affiliated; strongest verified coverage of **giải ngân đầu tư công** — the exact beat the user wants from baodautu, at a fraction of the effort. |
| Priority | **P1** — highest value/effort ratio in the plan |
| Implementation status | 🔲 Not started |
| Review status | 🔲 Not reviewed |

## Key insights

- **Feed pattern verified:** `https://thoibaotaichinhvietnam.vn/{category}/rss_feed/` → 200, 25 items,
  for all ~16 categories. (`/rss_feed/{category}` also works; `{category}.rss` → 404.)
- **Dates are clean:** `<meta property="article:published_time" content="2026-09-07T14:30:03+07:00">`
  — real ISO with real `+07:00`. No bespoke parsing (contrast: baodautu).
- **Feed ships `<content:encoded>` with the full body.** Tempting shortcut — but inline HTML is
  *not* Bronze. Phase-01's class fetches the detail page regardless (byte-exact WORM) and uses
  inline only as a failure fallback. Keep it that way.
- **Detail selectors verified:** body `div.article-detail-main` / `div.article-content`;
  sapo `div.article-detail-desc`; author `div.article-detail-author`; tags `div.article-tags`.
- **robots.txt verified:** `Allow: /` with `Disallow: /article/ /tag/ *.pdf *.xls *.xlsx *.doc *.docx`
  (+ ajax/api/admin paths). Article details live at **root** `/<slug>-<id>.html`, so `/article/`
  does **not** block them. **Never fetch `.pdf`/`.xls` attachments** — `RobotsGate` will refuse
  anyway, but the scraper must not be extended to chase them.
- **Config name matters:** name it **`thoibaotaichinhvietnam`**, not `tbtc`. `scripts/domain_check.py:152`
  and `src/monitor/domain_reporter.py:126,170` do `f"{dom}.vn" if "." not in dom else dom` — a `tbtc`
  name would silently query `tbtc.vn` and report 0 articles / false anomalies (scout-01 §c).
  Matching the host stem sidesteps the hack entirely (phase-03 fixes it properly).

## Requirements

**Functional**
1. 9 market-relevant categories ingested (not all 16 — noise control).
2. Bronze artifact per article; Silver derives with non-empty `cleaned_text`.
3. `published_at` = the feed/meta ISO `+07:00`, unmodified.
4. `language: vi`.

**Non-functional**
- **Zero new Python.** If this phase needs a code change, phase-01's class is wrong — fix it there.
- Cycle cost bounded: 9 feed fetches + ≤40 details ≈ 27 s + 120 s ≈ 150 s, inside the 15-min interval.
- Bronze non-negotiables per [plan.md](plan.md#global-non-negotiables-every-phase).

## Architecture

Identical to phase-01's flow. No new components:

```
config/domains/thoibaotaichinhvietnam.yaml (method: rss_capture)
   → REGISTRY["_rss_capture"] → RssCaptureScraper
   → Bronze: data/raw_html/thoibaotaichinhvietnam.vn/<yyyymmdd>/<hash>.{html,meta.json}
   → Silver: data/silver/thoibaotaichinhvietnam.vn/<yyyymmdd>/<hash>.json
```

Category selection = the 9 with market signal. Excluded (verified to exist, deliberately skipped):
`xa-hoi`, `doi-thoai`, `dien-dan-tai-chinh`, `su-kien-doanh-nghiep`, `thoi-su`, `phap-luat`,
`bat-dong-san`. Revisit after 1 week of volume data — do not front-load noise.

## Related code files

**Create**
| Path | Note |
|---|---|
| `project/config/domains/thoibaotaichinhvietnam.yaml` | the whole source |
| `project/tests/test_thoibaotaichinhvietnam.py` | config-level test on `RssCaptureScraper` |
| `project/tests/fixtures/tbtc_capture_feed.xml` | trimmed real feed bytes (keep `content:encoded`) |
| `project/tests/fixtures/tbtc_detail_page.html` | one real article page (verified ~22.7 KB) |
| `project/domains/thoibaotaichinhvietnam/schema.yaml` | contract; `domain: thoibaotaichinhvietnam.vn` |
| `project/domains/thoibaotaichinhvietnam/README.md`, `changelog.md` | monitor-doc convention |

**Modify**
| Path | Change |
|---|---|
| `project/docs/domains/README.md` | new matrix row (#24), line 3 count 23→24, line 34 vi/en stats |
| `project/docs/domains/vn-rss.md` | line 3 count; new `### thoibaotaichinhvietnam` section |
| `project/docs/skills/rss-sources.md` | feed-inventory row: 9 feeds, `rss_feed/` pattern, robots note |
| `project/README.md` | source counts (`:115-119`) |
| `project/scripts/sample_articles.py` | *(optional, cosmetic)* add to `GROUPS[...]["domains"]`; otherwise auto-falls into `03-vn-press-rss` |

**No change:** `src/scrapers/*` (none), `src/orchestrator.py`, `src/core/config.py`, `src/pipeline/*`,
`src/scrapers/__init__.py` (no new module), `config/watchlist.yaml`, `config/entities/*`.

## Implementation steps

### Step 1 — Measure volume before committing to 9 feeds
```bash
for c in chung-khoan tai-chinh chinh-sach-tai-chinh dau-tu thue-hai-quan \
         ngan-hang-bao-hiem doanh-nghiep thi-truong tai-chinh-quoc-te; do
  n=$(curl -sL -A "Mozilla/5.0" "https://thoibaotaichinhvietnam.vn/$c/rss_feed/" | grep -c "<item>")
  echo "$c $n"
done
curl -sL https://thoibaotaichinhvietnam.vn/robots.txt
```
Resolves researcher-03 open question #5 (volume/day not measured; 25 items is a page cap).
If any category is a firehose, add `filter.any` — but note `RssCaptureScraper` as specified in
phase-01 does **not** implement `filter`. If filtering turns out to be needed, port the
`filter`/`block_terms` block from `RSSScraper.parse_item` into `RssCaptureScraper` (phase-01
change, not a fork here).

### Step 2 — `config/domains/thoibaotaichinhvietnam.yaml`
```yaml
name: thoibaotaichinhvietnam   # KHỚP host stem — tránh bẫy .vn-suffix của domain_check.py:152
enabled: true                  # NEW SOURCE 2026-09-07 (verified curl: 9/9 feed 200, 25 items)
method: rss_capture            # RSS list + Bronze full capture (phase-01)
rate_limit: 3.0
timeout: 30
language: vi
base_url: "https://thoibaotaichinhvietnam.vn/"
rss:
  feeds:
    - {url: "https://thoibaotaichinhvietnam.vn/chung-khoan/rss_feed/",          name: "TBTC Chứng khoán"}
    - {url: "https://thoibaotaichinhvietnam.vn/tai-chinh/rss_feed/",            name: "TBTC Tài chính"}
    - {url: "https://thoibaotaichinhvietnam.vn/chinh-sach-tai-chinh/rss_feed/", name: "TBTC Chính sách tài chính"}
    - {url: "https://thoibaotaichinhvietnam.vn/dau-tu/rss_feed/",               name: "TBTC Đầu tư"}
    - {url: "https://thoibaotaichinhvietnam.vn/thue-hai-quan/rss_feed/",        name: "TBTC Thuế - Hải quan"}
    - {url: "https://thoibaotaichinhvietnam.vn/ngan-hang-bao-hiem/rss_feed/",   name: "TBTC Ngân hàng - Bảo hiểm"}
    - {url: "https://thoibaotaichinhvietnam.vn/doanh-nghiep/rss_feed/",         name: "TBTC Doanh nghiệp"}
    - {url: "https://thoibaotaichinhvietnam.vn/thi-truong/rss_feed/",           name: "TBTC Thị trường"}
    - {url: "https://thoibaotaichinhvietnam.vn/tai-chinh-quoc-te/rss_feed/",    name: "TBTC Tài chính quốc tế"}
detail:
  extract_full: true
  content_selector: "div.article-detail-main, div.article-content"   # verified 2026-09-07
  max_details_per_cycle: 40
capture:
  raw_dir: "data/raw_html"
  min_body_bytes: 2048
compliance:
  respect_robots: true
  proxy_rotation: false
  proxies: []
pitfalls: "Feed pattern = /{category}/rss_feed/ (KHÔNG phải {category}.rss → 404). Feed CÓ content:encoded full body nhưng vẫn fetch detail để giữ Bronze byte-exact; inline chỉ là fallback khi capture fail. published_time ISO +07:00 sạch. robots: Disallow /tag/ /article/ *.pdf *.xls — bài chi tiết nằm ở ROOT /<slug>-<id>.html nên KHÔNG bị chặn; TUYỆT ĐỐI không fetch attachment PDF/XLS. Verified live 2026-09-07."
```

### Step 3 — Fixtures
Save one real feed response and one real article page **byte-exact** into
`tests/fixtures/`. Trim the feed to 2–3 `<item>` but keep the XML declaration, the
`content:encoded` element and the `<link>` values intact.

### Step 4 — `tests/test_thoibaotaichinhvietnam.py`
Same shape as `tests/test_vneconomy.py`. `_config()` returns the YAML above as a dict.
Required cases:
- `test_capture_happy_path` — `capture_status == "ok"`; `source_domain == "thoibaotaichinhvietnam.vn"`;
  `published_at.endswith("+07:00")`; `metadata["language"] == "vi"`;
  `Path(cap["html_path"]).read_text(encoding="utf-8") == detail_html` (byte-exact)
- `test_content_selector_hits` — `missing` does **not** contain `main_content_node`
  (i.e. `div.article-detail-main` really matched the fixture)
- `test_inline_not_used_when_capture_ok` — `content_html` derives from the detail page,
  not from `content:encoded` (assert it contains a marker unique to the detail fixture)
- `test_detail_failure_falls_back_to_inline` — `detail_html=None`, `backoff=None` →
  `capture_status == "failed"`, `content_text` non-empty from inline, error recorded
- `test_max_details_cap` — cap honoured, `detail_deferred` on the overflow

### Step 5 — `domains/thoibaotaichinhvietnam/{schema.yaml,README.md,changelog.md}`
`schema.yaml` mirrors `domains/vietstock/schema.yaml`; top-level `domain: thoibaotaichinhvietnam.vn`,
`method: rss_capture`, `last_verified: 2026-09-07`, the robots/`rss_feed` pitfalls, and
`output_fields` health thresholds (`published_at` 1.0 — this source has clean dates, hold it to it).

### Step 6 — Docs
Matrix row #24 · `vn-rss.md` section · `skills/rss-sources.md` feed inventory · root `README.md` counts.
Call out in `vn-rss.md` that TBTC is the designated **KTXH/đầu tư công proxy** while NSO is blocked
(cross-link phase-05).

### Step 7 — Live smoke
```bash
cd project
python scripts/diagnose_sources.py thoibaotaichinhvietnam
python -m src.orchestrator --once thoibaotaichinhvietnam
python scripts/run_once.py thoibaotaichinhvietnam
```

### Step 8 — Evidence into `domains/thoibaotaichinhvietnam/changelog.md`

## Todo list

- [ ] 1. Measure per-feed volume + fetch robots.txt; confirm 9-feed set (or trim)
- [ ] 2. Write `config/domains/thoibaotaichinhvietnam.yaml`
- [ ] 3. Capture real fixtures (feed XML + detail HTML)
- [ ] 4. `tests/test_thoibaotaichinhvietnam.py` (5 cases); `pytest -q` green
- [ ] 5. `domains/thoibaotaichinhvietnam/{schema.yaml,README.md,changelog.md}`
- [ ] 6. Docs: matrix #24, `vn-rss.md`, `skills/rss-sources.md`, root `README.md`
- [ ] 7. Live smoke: diagnose → `--once` → `run_once.py`
- [ ] 8. Evidence into changelog

## Success criteria

| # | Check | Command / evidence |
|---|---|---|
| S1 | Tests green | `pytest -q` |
| S2 | Zero new Python | `git diff --stat src/` shows **no** change under `src/` for this phase |
| S3 | Parse health | `python scripts/diagnose_sources.py thoibaotaichinhvietnam` → 0 errors, 9 feeds parsed |
| S4 | Cycle clean | `python -m src.orchestrator --once thoibaotaichinhvietnam` → `new>0`, `errors=0` |
| S5 | **Bronze artifact** | `data/raw_html/thoibaotaichinhvietnam.vn/<yyyymmdd>/<hash>.html`; `sha256sum` == `.meta.json` `content_sha256`; `capture_status: "ok"`; `http_status: 200` |
| S6 | Bronze WORM | second cycle does not alter an existing `.html`'s bytes |
| S7 | **Silver derive** | `python scripts/run_once.py thoibaotaichinhvietnam` → `data/silver/thoibaotaichinhvietnam.vn/<yyyymmdd>/<hash>.json`, non-empty `cleaned_text`, `built_from_raw_path` → S5 |
| S8 | Date integrity | `python scripts/verify_quality.py thoibaotaichinhvietnam.vn` → **100%** `date` (this source has no excuse) and ≥95% overall |
| S9 | Selector health | `missing: ["main_content_node"]` absent from ≥95% of the cycle's `.meta.json` |
| S10 | No drift | `python scripts/report_drift.py` → no new `SELECTOR_BROKEN`/`TEMPLATE_DRIFT` for this domain |
| S11 | Robots respected | no `.pdf`/`.xls` path appears in any `.meta.json` `source_url`; no `capture_status: skipped_robots` on article URLs |
| S12 | Monitoring wired | `python scripts/domain_check.py report thoibaotaichinhvietnam` returns field-health (proves the name/host match works) |

## Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| 9 feeds × 25 items → detail cap 40 starves some categories | Med | Med | Cap is per cycle at 15-min cadence = 3840 details/day, far above real volume; Step 1 measures. If it bites, raise cap or drop low-signal feeds |
| Someone "optimises" by using `content:encoded` and skipping detail fetch | Med | **High** — silently breaks Bronze | S2 + S5 + `test_inline_not_used_when_capture_ok` all fail loudly; documented in `pitfalls:` |
| `rss_feed/` trailing-slash form changes upstream | Low | High | `domains/<name>/schema.yaml` + `report_drift.py`; `/rss_feed/{category}` is a verified alternate |
| Category overlap with vietnambiz/vneconomy inflates near-duplicates | Med | Low | `DedupCache.is_similar_title` fuzzy dedup is already on by default (`fuzzy_dedup: true`) |
| `thoibaotaichinhvietnam` is a long config name in every CLI invocation | Low | Trivial | Accepted — correctness over typing; phase-03's fix would allow a short alias later |

## Security considerations

- `respect_robots: true`. robots disallows `*.pdf`/`*.xls`/`/tag/` — the scraper only ever
  requests feed URLs and root article URLs; **do not** add attachment fetching here (that is
  phase-05's problem shape, and it is deferred).
- `rate_limit: 3.0` + `SourceBackoff` on 429/503.
- Government-affiliated publisher: stay conservatively polite; a block here is reputationally
  worse than a missed article.
- No auth, no secrets, no cookies persisted (`RawStore._filter_headers` whitelist).
- Bronze `.html` is third-party content: WORM, internal use, not redistributed.

## Next steps

→ [phase-03-tnck-capture-upgrade.md](phase-03-tnck-capture-upgrade.md) (independent of 01/02;
may run in parallel with phase-04).

## Unresolved questions

1. **TBTC volume/day** (researcher-03 §Unresolved #5) — 25 items/feed is a page cap, not a rate.
   Resolved by Step 1; determines whether `max_details_per_cycle: 40` and the 9-feed set are right.
2. **Filtering** — `RssCaptureScraper` as specced has no `filter.any`/`none`. If Step 1 shows a
   noisy category, that is a **phase-01 change** (port the block from `RSSScraper.parse_item`),
   not a local fork. Decide before shipping.
3. **Category set** — 9 chosen for market signal; `bat-dong-san` and `phap-luat` are plausible
   additions. Revisit after a week of data. Needs an owner call.
4. **Overlap accounting** — TBTC + baodautu + vneconomy all cover đầu tư công. Is near-duplicate
   coverage desirable (corroboration) or noise (dedup pressure)? Affects whether phase-04's
   scope can be trimmed.
