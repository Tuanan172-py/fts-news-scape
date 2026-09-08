# Research 03 — LIVE verification (curl, main agent), 2026-09-07

Supersedes unverified claims in researcher-01/02. Everything below = **fetched live today**
with browser UA. `[V]` = verified this session. Numbers = actual observed.

---

## 1. TNCK — tinnhanhchungkhoan.vn

### 1.1 RSS: DOES NOT EXIST [V]
| URL | Result |
|---|---|
| `/rss.html` | 200, **13 bytes**, empty |
| `/rss/trang-chu.rss`, `/chung-khoan.rss`, `/rss/chung-khoan.rss` | **302 redirect**, 0 bytes |

→ **JSON API is the only ingestion route.** Existing `src/scrapers/tnck.py` approach is correct.

### 1.2 Zone-ID map — FULL SWEEP [V] (`api/morenews-zone-{z}-1.html`, 40 items/page)
| zone | name | zone | name | zone | name |
|---|---|---|---|---|---|
| **1** | **Chứng khoán** | 17 | Lịch sự kiện | 34 | Chứng khoán (dup) |
| 2 | Quy hoạch | 18,19,15,20 | *(empty)* | 35 | Chính trị |
| 3 | Doanh nhân | **21** | **Pháp luật** | **36** | **Đầu tư** |
| **4** | **Thông tin doanh nghiệp** *(current cfg)* | 22 | Cung - Cầu | 37 | Xã hội |
| 5 | Bảo hiểm | 23 | Phong thủy | 38 | Địa ốc |
| **6** | **Tiền tệ** | 24 | Doanh nhân | **39** | **Vĩ mô** |
| 7 | Chính trị | 25 | Tiêu dùng | 41 | Tư vấn tài chính |
| **8** | **Điều tra** | **26** | **Mua bán - Sáp nhập (M&A)** | 42 | Quy hoạch |
| 9,12 | Quốc tế | 27,45 | DN tự giới thiệu *(PR — avoid)* | **43** | **Thương trường** |
| 10 | Tòa soạn (3 items) | 28 | Thông báo - bố cáo | 44 | Trải nghiệm sống |
| **11** | **Trái phiếu** | **29** | **Đại hội cổ đông** | 30 | Địa ốc (1 item) |
| **13** | **Nhận định** | 31,32 | Cộng đồng / Sản phẩm | 14,16 | *(no name)* / VIR |
| 33 | Pháp đình | | | | |

**Recommended zone set for user's goal** (điều tra DN / tranh chấp cổ đông / pháp lý CK):
`[1, 4, 8, 11, 21, 26, 29, 33, 39, 6]` — Chứng khoán, TT doanh nghiệp, Điều tra, Trái phiếu,
Pháp luật, M&A, ĐHCĐ, Pháp đình, Vĩ mô, Tiền tệ.
⚠️ Caveat: zone 8 "Điều tra" sampled titles are **general crime/consumer**, not purely corporate
("Bộ Công an: Huấn…", "Fanpage tích xanh giả mạo…"). Corporate-legal signal is concentrated in
**21/33/26/29**, not 8. Recommend keyword filter or lower priority for zone 8.

### 1.3 API facts [V]
- `Content-Encoding: gzip`, `Content-Type: application/json;charset=utf-8`, `Server: WT_11.11`.
- `"date": 1788494299` → **JSON number, NOT string** (repo docs say "string"). `int()` works either way; docs need correction.
- `zone` object echoes `zone_id` + `name` per item → categories self-describing, no lookup table needed.

### 1.4 robots.txt [V] — `www.tinnhanhchungkhoan.vn/robots.txt`
```
User-Agent: *   Allow: /
Disallow: /api/  /search/  /tim-kiem/  /search.html  /tim-kiem.html  /tu-khoa.html  /tag.html  /print.html
Sitemap: https://www.tinnhanhchungkhoan.vn/sitemap.xml
```
- `Disallow: /api/` is on **www**, NOT on `api.tinnhanhchungkhoan.vn` (separate host, its own robots.txt = 200/empty).
- Article detail paths `/<slug>-post<NNN>.html` → **allowed**. `RobotsGate` passes.
- No `Crawl-delay` declared → repo default 3.0s stands.

### 1.5 Article detail [V] (`/co-phieu-chung-khoan-chi-bao-thi-truong-post397097.html`, 106,262 B)
| Field | Selector / source |
|---|---|
| body | `div.article__body.cms-body` → `content_selector: "div.article__body"` |
| sapo | `div.article__sapo.cms-desc` |
| meta | `div.article__meta`; tags `div.article__tag` |
| published | `<meta property="article:published_time" content="2026-09-07T12:48:05+0700"/>` **and** `<time class="time" datetime="…+0700" data-time="1788760085">` |
| wrapper | `div.wrapper.detail-page`, `div.main-column.article` |
- Server-rendered, no JS needed. Ads live in `div[id^=adsWeb_]` (inside body — strip downstream).
- `article.url` uses **`www.`** host; current `tnck.py` hardcodes `source_domain="tinnhanhchungkhoan.vn"` (no www) → Bronze path/domain consistency check needed.

---

## 2. Báo Đầu Tư — baodautu.vn

### 2.1 RSS: PERMANENTLY BROKEN — do not use [V]
All 8 probed feed URLs return HTTP 200 + **0 `<item>`**, ~1.2 KB. Root cause found:
every category feed serves the **same empty home channel** —
```xml
<title>Trang chủ</title>
<link>https://baodautu.vn//.rss</link>   <!-- malformed: double slash, no category -->
```
→ Server-side RSS generator is broken, not "dormant/temporarily empty". Existing
`config/domains/baodautu.yaml` comment ("bật lại khi feed có items") is **not actionable**;
close it out. Confirms the 2026-07-24 disable decision, 14 months on.
Also: `rssMain.html` returns the **HTML homepage** (34 KB), not a feed.

### 2.2 robots.txt: fully permissive [V]
```
User-agent: *
Allow: /
Sitemap: https://baodautu.vn/sitemap.xml
```
No Disallow, no Crawl-delay.

### 2.3 Sitemap = recommended list route [V]
- `sitemap.xml` = sitemapindex → `sitemaps/categories.xml` + **`sitemaps/news-YYYY-M.xml`** (monthly, back to 2025+).
- `sitemaps/news-2026-9.xml`: **102,206 B, 348 `<url>`** for Sep 1–7 → **~50 articles/day** [V].
- Entry shape: `<loc>` (whitespace-padded, needs `.strip()`), `<lastmod>` date-only `2026-09-07`, `changefreq`, `priority`.
- ⚠️ **Sitemap carries no category and no time-of-day** → cannot target "đầu tư công/FDI" and gives poor freshness ordering. Use sitemap only as a **completeness backstop**, not the primary list.

### 2.4 Category listing = recommended primary route [V]
Full category set from `sitemaps/categories.xml` (pattern `<slug>-d<N>/`):
| Category | Path | Relevance |
|---|---|---|
| **Toàn cảnh đầu tư** | `/toan-canh-dau-tu-d2/` | **đầu tư công, giải ngân, FDI, hạ tầng** ★ |
| **Thời sự Đầu tư** | `/thoi-su-dau-tu-d1/` | chính sách vĩ mô ★ |
| **Đầu tư tài chính** | `/dau-tu-tai-chinh-d6/` | chứng khoán/tài chính ★ |
| **Kinh doanh** | `/kinh-doanh-d3/` | doanh nghiệp ★ |
| Ngân hàng & Bảo hiểm | `/ngan-hang--bao-hiem-d5/` | *(note double dash)* ★ |
| Thị trường địa ốc | `/thi-truong-dia-oc-d7/` | BĐS |
| Đầu tư và Pháp luật | `/dau-tu-va-phap-luat-d41/` | pháp lý |
| Quốc tế `d54`, Doanh nhân `d4`, Kinh tế số `d77`, PT bền vững `d52`, KH&CN `d10`, Tiêu dùng `d8`, Sức khỏe DN `d53`, Du lịch `d55`, Đời sống `d27`, Ô tô xe máy `d9`, Y tế `d78`, Điểm tin `d76`, TT doanh nghiệp `d36`, **Quảng bá `d80` (PR — exclude)** | | |

- `d2` page 1: **48,558 B, 31 unique article links**, server-rendered [V].
- **Pagination RESOLVED [V]:** anchors are `<a href="p2" class="pagation_item">` (relative).
  Absolute form = **`https://baodautu.vn/<slug>-d<N>/p<page>`** — verified `…/toan-canh-dau-tu-d2/p2`
  → 200, 49,658 B, 34 article links, `pagation_item active` correctly on p2.
  ⚠️ **Trailing slash breaks it:** `…/p2/` → **404**. Page 1 = bare `…-d2/` (with slash).
- Listing item markup [V]: `div.thumbblock.thumb275x155`, title `a.title_thumb_square.fbold`,
  sapo `div.sapo_thumb_news`, category label `span.cl_green`. **No publish datetime on the
  listing page** — date is detail-only.
- No dedicated top-level FDI or "hạ tầng/quy hoạch" category exists — they live inside `d2`. Ticker/keyword filter needed if narrower targeting wanted.

### 2.5 Article detail [V] (`…-d695520.html`, 61,630 B, 37 `<script>`)
| Field | Selector |
|---|---|
| **body** | **`#content_detail_news`** ← the only correct one |
| title | `div.title-detail` (⚠️ **no `<h1>` on page at all**) |
| sapo | `div.sapo_detail` |
| tags | `div.tag_detail` > `.tag_detail_item` |
| wrapper | `main.main_content.main_detail` |
| published | plain text `07/09/2026 10:38` — **no `<time>`, no `article:published_time`, no JSON-LD** ⚠️ |
- Body paragraphs are `<p class="p1" style="text-align: justify;">`, HTML-entity encoded (`&ecirc;`). Server-rendered.
- ⚠️ **Trap:** `<div class="content">'+content+'</div>'` exists as a **JS template string** for the comment widget — a naive `.content` selector grabs the wrong node. Must use `#content_detail_news`.
- ⚠️ **Date parsing is bespoke:** `dd/MM/yyyy HH:mm` scraped from listing or detail text, assume `+07:00`. No standard metadata to fall back on.

---

## 3. VietnamBiz — vietnambiz.vn [V]

RSS **alive and healthy**, 30 items/feed:
| Feed | items | bytes |
|---|---|---|
| `/chung-khoan.rss` | 30 | 31,334 |
| `/tai-chinh.rss` | 30 | 31,745 |
| `/vi-mo.rss` | 30 | 30,493 |
| **`/doanh-nghiep.rss`** (NEW) | 30 | 30,931 |
| **`/nha-dat.rss`** (NEW) | 30 | 31,448 |
| **`/hang-hoa.rss`** (NEW) | 30 | 35,922 |
| `/quoc-te.rss` | **0** | 356 — dead, skip |

→ Existing `config/domains/vietnambiz.yaml` (3 feeds, `enabled: false` since 2026-08-03) can be
re-enabled and **extended by 3 feeds**. Known encoding quirk (declares utf-16, serves utf-8) is
already handled by `_decode_feed`. Lowest-effort win in this whole plan.

---

## 4. Thời báo Tài chính Việt Nam — thoibaotaichinhvietnam.vn [V]

**NEW source, not in repo. RSS works and is high quality.**

- Feed discovery: `<link rel="alternate" type="application/rss+xml" href="https://thoibaotaichinhvietnam.vn/rss_feed/">`
- **Per-category pattern (all 200, 25 items each) [V]:**
  `https://thoibaotaichinhvietnam.vn/{category}/rss_feed/`
  (also works: `/rss_feed/{category}` and `/rss_feed/{category}/`; `{category}.rss` → 404)
- **Feed ships `<content:encoded>` with full article body** [V] → detail fetch optional; still fetch for Bronze byte-exactness.
- Categories [V]: `chung-khoan`, `tai-chinh`, `chinh-sach-tai-chinh`, `thue-hai-quan`,
  `ngan-hang-bao-hiem`, `doanh-nghiep`, `dau-tu`, `bat-dong-san`, `thi-truong`, `thoi-su`,
  `tai-chinh-quoc-te`, `dien-dan-tai-chinh`, `phap-luat`, `xa-hoi`, `doi-thoai`, `su-kien-doanh-nghiep`.
- Article URL: `/<slug>-<id>.html` at root.
- Detail [V] (22,725 B): body `div.article-detail-main` / `div.article-content`;
  sapo `div.article-detail-desc`; author `div.article-detail-author`; source `div.article-detail-source`;
  tags `div.article-tags`; **`<meta property="article:published_time" content="2026-09-07T14:30:03+07:00">`** (clean ISO+07).
- **robots.txt [V]:** `Allow: /` + `Disallow:` `/ajax/ /sp/ /services/ /utilities/ /apiservice@/ /apicenter@/ /widgets@/ /member.api/ /preview_article/ /stats/ /slie/ **/article/** /login/ /administrator/ /act/ /adsfw/ **/tag/** *.pdf *.xls *.xlsx *.doc *.docx`.
  ⚠️ Article detail pages live at **root** (`/<slug>-<id>.html`), so `Disallow: /article/` does **not** block them. But `*.pdf`/`*.xls` disallowed → **do not** fetch attachments.
- Strong on **giải ngân đầu tư công** (top feed item today: "Infographics 8 tháng giải ngân vốn đầu tư công cả nước đạt 509.557,5 tỷ đồng") — overlaps the exact beat the user wants from baodautu, at a fraction of the effort.

---

## 5. NSO / Cục Thống kê — **BLOCKED, cannot build now** [V]

| Probe | Result |
|---|---|
| DNS `www.nso.gov.vn` | resolves → **160.25.148.3** |
| `https://www.nso.gov.vn/` | `curl (35) Recv failure: Connection was reset` |
| `http://www.nso.gov.vn/` | `curl (56) Recv failure: Connection was reset` (TCP connects, then RST) |
| `https://www.gso.gov.vn/` | timeout after 20 s |
| researcher-02 WebFetch (different egress) | 4/4 `ECONNRESET` |

→ Reset happens **after TCP connect, before any HTTP response**, on both :80 and :443, from two
different network paths. Cause is either the FPT corporate egress filter or an NSO
WAF/geo-IP block. **Not diagnosable from here.**

**Consequence for the plan:** NSO must be a *separate, gated phase*. Do not write a scraper until
connectivity is proven **from the actual deployment host**. Cheap mitigations to evaluate first:
(a) test from the prod box / a VN residential line, (b) use TBTC + baodautu as **proxies** for NSO
content — both republish the monthly KTXH report within hours, (c) `nso.gov.vn` may serve an
alternate host/CDN.

Design note (if it ever unblocks): NSO items are **periodic structured reports (~1/month + CPI/IIP/FDI
series)**, not a news stream — needs dedup by **report period + report type**, not by URL, and PDF/XLSX
attachment handling. This does **not** fit `BaseScraper.run()` cleanly and is genuinely a different
component. Treat as its own design, not a 24th domain YAML.

---

## Effort/value ranking (derived from the above)

| Rank | Source | Effort | Route | Note |
|---|---|---|---|---|
| 1 | **vietnambiz** | ~0 (YAML only) | RSS ×6 | flip `enabled`, +3 feeds |
| 2 | **TBTC** *(new)* | low (YAML + capture scraper) | RSS ×N + capture | clean ISO dates, content:encoded, great đầu tư công coverage |
| 3 | **TNCK** | low-med (upgrade existing) | API zones + capture | add CaptureMixin, expand zones 4 → 10 |
| 4 | **baodautu** | **high** | HTML listing + sitemap | no RSS, no `<h1>`, no date metadata, bespoke everything |
| 5 | **NSO** | blocked | — | network reset; re-scope |

---

## Unresolved questions
1. ~~baodautu pagination URL format~~ — **RESOLVED** [V]: `…-d<N>/p<page>`, no trailing slash.
2. ~~baodautu listing publish datetime~~ — **RESOLVED** [V]: **not on listing**, detail-only.
   Consequence: cannot order/filter by freshness before fetching detail → must rely on listing
   order (newest first, assumed) + `seen_articles` dedup, or cross-check `lastmod` from
   `sitemaps/news-YYYY-M.xml` (date-only granularity).
3. **TNCK zone 8 "Điều tra"** — worth including given general-crime skew, or rely on 21/33/26/29?
4. **TNCK www vs non-www** `source_domain` — normalize to which? Affects Bronze partition path + `verify_quality.py` args + dedup continuity with existing rows.
5. **TBTC volume/day** — not measured (25 items/feed is a page cap, not a daily rate).
6. **NSO** — is the reset FPT egress or NSO-side? Needs a test from outside the corporate network.
7. `zone 14` / `zone 16` TNCK returned 40 items with no/odd `name` — unmapped.
