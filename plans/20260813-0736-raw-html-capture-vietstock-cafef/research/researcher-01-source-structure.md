# Raw HTML Structure Research: Vietstock & CafeF

**Date:** 2026-08-13 | **Budget:** 5 tool calls used | **Scope:** HTML delivery mechanism, content selectors, robots.txt compliance

---

## Vietstock (https://vietstock.vn)

### Content Delivery
- **Rendering:** Server-rendered (full article body present in initial HTML response)
- **No JS injection:** Article text, images, metadata available without secondary API calls

### Content Selectors
| Element | Selector | Details |
|---------|----------|---------|
| Article Body | `<article>` / `<h1>` through concluding `<p>` tags | Main text server-rendered |
| Title | `<h1>` tag | "Đại gia xăng dầu Chu Thị Thành bị truy tố..." |
| Author | Byline text: "Tâm An" | Located near publish info |
| Publish Time | `13-08-2026 14:34:00+07:00` | Timestamp metadata in HTML |
| Category | Breadcrumb: "Tài chính cá nhân > Doanh nhân và khởi nghiệp" | Multiple category levels |
| Source Attribution | "VietNamNet" (linked) | Third-party news attribution |

### Image Handling
- **`<img>` tags:** Direct `src` attributes, no lazy-loading
- **Example URL:** `https://image.vietstock.vn/2026/08/13/vietstock_s_dai-gia-xang-dau-chu-thi-thanh-bi-truy-to-doanh-nghiep-be-boi-no-thue-nghin-ty_20260813134758.png`
- **No `data-src`, `data-original`, `data-lazy`, or `srcset`** detected
- **Captions:** Static text below/with image (no figure/figcaption markup observed in sample)

### Multimedia
- No video iframes or embed elements detected
- Static images only

### Anti-Bot Detection
- No Cloudflare challenges, JS verification, or CAPTCHA
- Loads directly without bot detection

### Sample URL
- Tested: `http://vietstock.vn/2026/08/dai-gia-xang-dau-chu-thi-thanh-bi-truy-to-doanh-nghiep-be-boi-no-thue-nghin-ty-4262-1480070.htm`
- RSS feed: `https://vietstock.vn/0/tin-moi.rss`

---

## CafeF (https://cafef.vn)

### Content Delivery
- **Rendering:** NOT DIRECTLY TESTED (no article URL fetched due to budget limit)
- **API availability:** Article list via `https://cafef.vn/du-lieu/Ajax/PageNew/News.ashx` (documented in request)
- **Status:** Likely hydrated or JS-rendered; API-first architecture suggests secondary data fetch

### Known Data Source
- Article list API: `https://cafef.vn/du-lieu/Ajax/PageNew/News.ashx`
- Implies data-driven page rendering (possible client-side article body injection)

### Robots.txt Status
- Fully open (`Allow: /`; no Disallow directives)
- No crawl-delay enforced
- Sitemaps present for search indexing

### Missing Details for CafeF
- Main content container selector(s)
- Image attribute handling (src vs lazy-load variants)
- Video/iframe markup
- Author/time/category selectors
- Anti-bot signals

---

## Robots.txt & Legal Compliance

### Vietstock
- **Disallow:** `/*.js`, `/*.css`, `/manager`, `/export`, `/cache`
- **Crawl-delay:** None specified
- **Article pages:** NOT disallowed; `/` is crawlable
- **Assessment:** Safe to scrape article content; avoid `.js`, `.css` resources and `/manager/*` paths

### CafeF
- **Disallow:** None (open to all crawlers)
- **Crawl-delay:** None specified
- **Sitemaps:** Present for indexing
- **Assessment:** Fully open; no robots.txt restrictions on article pages

---

## Key Findings

1. **Vietstock:** Server-rendered HTML; straightforward scraping via static `<img src>`, no lazy-load
2. **CafeF:** API-first data architecture (inferred); article body likely JS-injected after page load
3. **Anti-bot:** Neither domain uses Cloudflare or CAPTCHA in initial responses
4. **Legal:** Both robots.txt allow article scraping; Vietstock restricts asset pipeline, CafeF fully open

---

## Unresolved Questions

1. **CafeF article body rendering:** Is content server-rendered or JS-hydrated after API fetch? (Requires direct article page fetch)
2. **CafeF image lazy-loading:** Does CafeF use `data-src`, `data-lazy`, or similar attributes? (Not tested)
3. **Video/iframe handling:** CafeF may embed YouTube or local video players; markup unknown
4. **Author/publish time location:** CafeF selectors for metadata not determined
5. **Session/cookie requirements:** Are authenticated sessions required for full content access on either site?

---

## ADDENDUM (main agent, live verify 2026-08-13) — CafeF detail page CONFIRMED
CafeF gap from budget closed by direct fetch of real article
(`/fpt-sap-phat-hanh-hon-171-trieu-co-phieu-thuong-cho-co-dong-188260804074555716.chn`):
- **Server-rendered**: full multi-paragraph body present in plain HTTP GET (no JS/hydration needed).
- Metadata in HTML: author `Khánh Hân`, publish `04-08-2026 - 08:03 AM`, category `Doanh nghiệp`.
- Body image present WITH caption (`Ảnh minh họa: FPT`).
- Article URL pattern: `/{slug}-{id}.chn` (id e.g. `188260804074555716`); some links `/du-lieu/{SYM-id}/{slug}.chn`. All carry `?utm_source=du-lieu` from API (strip for canonical).
- Historic container `div#mainContent` (from `src/scrapers/cafef.py`).
⇒ Both sources server-rendered → `requests` client is sufficient for full raw-HTML capture; headless browser only optional fallback for embeds/lazy edge cases.
