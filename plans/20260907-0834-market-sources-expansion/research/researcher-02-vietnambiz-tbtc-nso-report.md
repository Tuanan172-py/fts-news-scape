# Research: vietnambiz.vn, thoibaotaichinhvietnam.vn, NSO/GSO

## 1. vietnambiz.vn

Repo already has config: `project/config/domains/vietnambiz.yaml` — **currently `enabled: false`** (disabled 2026-08-03, "focus on cafef + vietstock only").

Existing working feeds (method: rss, verified 2026-07-25 per repo pitfalls note):
| Feed | URL |
|---|---|
| Chứng khoán | `https://vietnambiz.vn/chung-khoan.rss` |
| Tài chính | `https://vietnambiz.vn/tai-chinh.rss` |
| Vĩ mô | `https://vietnambiz.vn/vi-mo.rss` |

Pattern = `https://vietnambiz.vn/{category-slug}.rss`. Other category slugs seen in nav (untested as `.rss`, `[UNVERIFIED]`): `thoi-su`, `hang-hoa`, `quoc-te`, `nha-dat`, `chung-khoan`, `doanh-nghiep`, `kinh-doanh`, `du-bao`. Separate data portal: `https://data.vietnambiz.vn/` (not RSS, dashboard-like — out of scope for news scraping).

Config detail: `rate_limit: 3.0`, `timeout: 30`, `detail.extract_full: true`, `max_details_per_cycle: 30`. Known pitfall: feed XML declares `utf-16` but body bytes are actually `utf-8` — repo's `_decode_feed` strips the encoding attr to work around it (see fixture `project/tests/fixtures/vietnambiz_utf16.rss`).

Article-detail CSS selectors: **not re-verified this session** — repo code already implements `extract_full`; did not re-fetch an article page (budget). `[UNVERIFIED]` for selector strings — pull from existing scraper implementation for `vietnambiz` domain rather than re-deriving.

robots.txt, JS-rendering need, volume/day: not checked this session. `[UNVERIFIED]`.

## 2. thoibaotaichinhvietnam.vn

No existing repo config found (`grep -rli vietnambiz|thoibaotaichinh` under `project/` only matched vietnambiz files).

Homepage fetch succeeded; confirmed nav/category URLs:
`thoi-su`, `thoi-su/xay-dung-dang`, `tai-chinh`, `dau-tu`, `thue-hai-quan`, `chung-khoan`, `ngan-hang-bao-hiem` (+ subcats `ty-gia`, `lai-suat`, `gia-vang`), `doanh-nghiep`, `thi-truong`, `bat-dong-san`, `xa-hoi`, `phap-luat`, `tai-chinh-quoc-te` — all under `https://thoibaotaichinhvietnam.vn/{slug}`.

RSS: **no `<link rel="alternate" type="application/rss+xml">` detected** in the fetched (markdown-converted) homepage. Could be present in raw `<head>` but stripped by the fetch tool's HTML→markdown conversion, or genuinely absent. `[UNVERIFIED]` — recommend a raw `curl`/view-source check of `/rss` or `/rss.xml` before building a config; do not assume it exists.

Article selectors, robots.txt, JS-rendering, volume/day: not checked. `[UNVERIFIED]`.

## 3. NSO (nso.gov.vn) — PRIMARY MACRO SOURCE

**Site is unreachable via WebFetch — 4/4 attempts returned `ECONNRESET`** (homepage `/`, `/tin-tuc-thong-ke/`, `/en/monthly-report/`, `/robots.txt`). This is a connection-level reset, not an HTTP error — strong signal of a WAF/anti-bot layer (Cloudflare/Akamai/VN gov firewall) blocking non-browser clients rather than a JS-rendering-only requirement. **Flag for implementation: test with a real headless browser (Playwright, real UA/TLS fingerprint) or `curl-impersonate` before assuming plain `requests`/`httpx` will work at all.**

All URL patterns below come from Google-indexed snippets (WebSearch), NOT direct page fetch — treat structurally as reliable (real indexed URLs) but content/selectors as `[UNVERIFIED]`.

### URL patterns found (via WebSearch, all from 2026)
| Type | Path pattern | Example |
|---|---|---|
| Monthly report (VN) | `/tin-tuc-thong-ke/{YYYY}/{MM}/mot-so-net-chinh-tinh-hinh-kinh-te-xa-hoi-thang-{X}-va-{N}-thang-dau-nam-{YYYY}/` | `.../2026/05/mot-so-net-chinh-tinh-hinh-kinh-te-xa-hoi-thang-tu-va-4-thang-dau-nam-2026/` |
| Monthly report (alt path, same title) | `/bai-top/{YYYY}/{MM}/bao-cao-tinh-hinh-kinh-te-xa-hoi-thang-{X}-va-{N}-thang-dau-nam-{YYYY}/` | `.../bai-top/2026/05/bao-cao-tinh-hinh-kinh-te-xa-hoi-thang-tu-va-4-thang-dau-nam-2026/` |
| Quarterly "nét chính" | `/tin-tuc-thong-ke/{YYYY}/{MM}/mot-so-net-chinh-tinh-hinh-kinh-te-xa-hoi-quy-{ii}-va-{N}-thang-dau-nam-{YYYY}/` | `.../2026/07/...-quy-ii-va-6-thang-dau-nam-2026/` |
| Quarterly press release | `/du-lieu-va-so-lieu-thong-ke/{YYYY}/{MM}/thong-cao-bao-chi-ve-tinh-hinh-kinh-te-xa-hoi-quy-{ii}-va-{N}-thang-dau-nam-{YYYY}/` | `.../2026/07/thong-cao-bao-chi-ve-tinh-hinh-kinh-te-xa-hoi-quy-ii-va-sau-thang-dau-nam-2026/` |
| Press-conference event page | `/su-kien/{YYYY}/{MM}/hop-bao-cong-bo-so-lieu-thong-ke-kinh-te-xa-hoi-quy-{ii}-va-{N}-thang-dau-nam-{YYYY}/` | `.../2026/07/hop-bao-cong-bo-so-lieu-thong-ke-kinh-te-xa-hoi-quy-ii-va-6-thang-dau-nam-2026/` |
| EN mirror, monthly | `/en/data-and-statistics/{YYYY}/{MM}/report-socio-economic-performance-in-{month}-{YYYY}/` | `.../2026/03/report-socio-economic-performance-in-february-2026/` |
| EN mirror, quarterly | `/en/data-and-statistics/{YYYY}/{MM}/report-on-socio-economic-situation-in-quarter-{roman/word}-in-{YYYY}/` | `.../2026/04/report-on-socio-economic-situation-in-quarter-i-in-2026/` |
| EN monthly-report landing/index | `/en/monthly-report/` | (fetch failed, ECONNRESET) |

Observations:
- The **same report** appears to get published/mirrored under 2+ different path prefixes (`tin-tuc-thong-ke` vs `bai-top`, and VN vs `en/`) — **dedup risk**: same underlying report period, different URLs.
- Quarterly report absorbs "N tháng đầu năm" (N months into year) cumulative framing, i.e. Q2 report = "quý II và 6 tháng đầu năm". Semi-annual and quarterly are the same artifact, not separate.
- Annual report pattern not observed this session (not searched) — `[UNVERIFIED]`, but standard NSO practice almost certainly publishes one; needs a follow-up search e.g. "báo cáo tình hình kinh tế xã hội năm 2025 nso.gov.vn".
- CPI, IIP (chỉ số sản xuất công nghiệp), FDI, xuất nhập khẩu, bán lẻ hàng hóa as **standalone series pages/press releases** were NOT located this session (single WebSearch query used, budget-constrained). `[UNVERIFIED]` — likely live under `/du-lieu-va-so-lieu-thong-ke/` or a dedicated `/so-lieu-thong-ke/{topic}/` section; needs dedicated follow-up searches per series.
- Cadence: monthly report for month M appears published in month M+1 (e.g. Feb 2026 report path is dated `/2026/03/`) — consistent with "day ~6 of following month" convention widely cited for GSO/NSO, but the **exact publish day was not verified** (page not fetched, no timestamp seen). `[UNVERIFIED]`.
- RSS / sitemap.xml / JSON API: **not found, not confirmed absent** — could not check `/robots.txt` or `/sitemap.xml` due to ECONNRESET. `[UNVERIFIED]`. Given VN government sites rarely expose RSS, best assumption for now: **no RSS**, poll the listing pages `/tin-tuc-thong-ke/` and `/du-lieu-va-so-lieu-thong-ke/` (and EN `/en/monthly-report/`) directly.
- Artifact formats (PDF/XLSX/infographic) and their URL patterns: **not verified** (page body not loaded). `[UNVERIFIED]` — but NSO/GSO reports are historically known to attach PDF + XLSX data tables on detail pages; must confirm actual `<a href>` patterns once site is reachable.
- HTML selectors (title, publish date, body, category, tags, attachment links): **not derivable — 0 successful page loads**. `[UNVERIFIED]`.
- Volume/month: very low — realistically 1 monthly report + occasional quarterly/press-conference/press-release pages + (if separate) individual series releases (CPI, IIP, FDI, XNK, bán lẻ) ≈ single-digit to ~10 relevant pages/month. `[ESTIMATE, UNVERIFIED]`.

### Key design implication (NSO)
NSO items are **periodic structured reports**, not a news stream. This changes scraper design vs the other two sources:
- **Low-frequency, scheduled polling** (e.g. crawl listing pages a few times/month around expected publish windows), not continuous/interval polling.
- **Dedup key = report period + report type** (e.g. `("monthly", 2026, 4)` / `("quarterly", 2026, "Q2")`), NOT URL — because the same period's report is mirrored across `tin-tuc-thong-ke`, `bai-top`, `du-lieu-va-so-lieu-thong-ke`, `su-kien`, and `en/` paths with different URLs/titles.
- **Attachment-first value**: the PDF/XLSX data tables are likely higher value than the HTML narrative for downstream numeric extraction — bronze layer should fetch and store attachments as first-class artifacts, not just the HTML body.
- **High value / low volume** — worth a dedicated, careful, low-QPS crawler rather than the generic RSS-poll pattern used for news sites; a WAF workaround (headless browser or browser-fingerprint HTTP client) is a hard prerequisite before any of this can be implemented.

## Citations
Fetched successfully:
- https://vietnambiz.vn/ (WebFetch)
- https://thoibaotaichinhvietnam.vn/ (WebFetch)
- `project/config/domains/vietnambiz.yaml` (repo file)
- `project/tests/fixtures/vietnambiz_utf16.rss` (repo file, path only, not opened)

Fetched, failed (ECONNRESET, all nso.gov.vn):
- https://www.nso.gov.vn/
- https://www.nso.gov.vn/tin-tuc-thong-ke/
- https://www.nso.gov.vn/en/monthly-report/
- https://www.nso.gov.vn/robots.txt

WebSearch query used: `nso.gov.vn "báo cáo tình hình kinh tế xã hội" tháng 2026 site:nso.gov.vn` — surfaced URLs cited in section 3 table.

## Unresolved questions
1. NSO WAF/bot-block: does it also block real browsers from this network/IP, or only this fetch tool? Needs a manual/headless-browser test before deciding scraper architecture.
2. NSO exact publish day-of-month for monthly report — commonly cited as ~day 6, not verified here.
3. NSO RSS/sitemap.xml existence — unconfirmed either way.
4. NSO CPI/IIP/FDI/XNK/bán lẻ standalone series pages — URLs not located this session, needs dedicated searches.
5. NSO annual report URL pattern — not searched.
6. NSO article selectors (title/date/body/attachments) and actual PDF/XLSX link patterns — zero page loads succeeded, fully unknown.
7. thoibaotaichinhvietnam.vn RSS feed existence — homepage fetch showed none, but markdown conversion may have stripped `<head><link>` tags; needs raw HTML check.
8. vietnambiz.vn article-detail selectors — not re-verified this session; check existing scraper implementation code instead of re-deriving.
9. robots.txt constraints for vietnambiz.vn and thoibaotaichinhvietnam.vn — not checked.
10. Volume/day (or /month) estimates for all three sources — not measured, only estimated/guessed for NSO.
