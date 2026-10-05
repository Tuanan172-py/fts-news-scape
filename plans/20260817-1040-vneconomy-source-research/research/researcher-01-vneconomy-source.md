# VnEconomy Source Research Report
**Date:** 2026-08-17 | **Researcher:** Claude Code

---

## 1. RSS Feeds Status

### Feed Availability & Item Counts
All 3 configured feeds are **LIVE and active**:
- `https://vneconomy.vn/chung-khoan.rss` — 50 items (stock market)
- `https://vneconomy.vn/tai-chinh.rss` — 50 items (finance)
- `https://vneconomy.vn/thi-truong.rss` — 50 items (market)

### Content Encoding: Critical Finding
**NO `<content:encoded>` tags present in any feed.** Only `<description>` tags with brief summaries (1-3 sentences). Confirms repo pitfall: "content:encoded namespace declared but NOT populated — must detail-fetch."

### Metadata Quality
| Field | Status | Format |
|-------|--------|--------|
| **pubDate** | ✓ Present | RFC 2822 (e.g., "Mon, 17 Aug 2026 10:41:56 GMT") |
| **Timezone** | ✓ GMT | Consistent across all feeds |
| **Author** | ✓ Present | Text names (e.g., "Kim Phong", "Ban Truyền hình VnEconomy") |
| **Category** | ✓ Present | Multi-valued (e.g., "Chứng khoán", "Thế giới", "Video") |
| **Media** | ✓ Present | `<media:content>` + `<media:thumbnail>` with fixed dims (1200×630, 300×168) |

---

## 2. Article Detail Page Structure

### Test Article
**URL:** `https://vneconomy.vn/mua-ban-deu-chan-nan-thanh-khoan-roi-xuong-muc-thap-ky-luc.htm`

### Content Container & Selectors
- **Main content:** Semantic HTML, no specific wrapper class. Content flows naturally after breadcrumbs.
- **Title:** `<h1>` tag, directly after navigation
- **Author:** Text node "K Kim Phong" (space before surname indicates "K" as abbreviated first-name or byline marker)
- **Publish date:** Text format "15:33, 17/08/2026" (HH:MM, DD/MM/YYYY)
- **Category:** Visible as "Chứng khoán" link

### Image Handling
**Direct `src` attributes (NO lazy-loading).** Example:
```
src="https://premedia.vneconomy.vn/files/uploads/2026/08/17/9cb36685523148cdbbfd45a81e155bfd-112745.png?w=1200"
```
Images use CDN domain `premedia.vneconomy.vn` with width parameter (`?w=1200`).

### Rendering Method
**Fully server-rendered.** Article HTML, metadata, and structure present in initial response. No JavaScript required for core content. **Suitable for direct HTTP fetch + CSS parsing.**

### Protection Assessment
**No Cloudflare, no JS challenges.** Straightforward page structure. robots.txt does not block article paths.

---

## 3. robots.txt Compliance

### Disallow Rules
- `/api/` — API endpoints blocked
- `/v1/search` — Search API blocked
- `/Error/` — Error pages blocked
- `/*?nocache=true` & `/*&nocache=true` — Cache-bypass params blocked
- `/tim-kiem.html?` — Search page with query strings blocked

### RSS & Article Paths
**NOT blocked.** Explicitly allowed under catch-all `Allow: /`.

### Crawl Delay
**1-second delay** for AI bots (GPTBot, ClaudeBot, PerplexityBot, OAI-SearchBot).

**Implication:** Crawl-delay compliant scraper should throttle detail-fetch requests to ≥1s/request.

---

## 4. Stock Ticker & Section Coverage

### Identified Categories (from feed + homepage)
- "Chứng khoán" (Securities/Stock Market) — PRIMARY
- "Tài chính" (Finance) — PRIMARY
- "Thị trường" (Market) — PRIMARY
- "Đầu tư" (Investment)
- "Kinh tế xanh" (Green Economy)
- "Thế giới" (World/International)
- "Video" (Video content)
- "eMagazine" (Magazine)

### Ticker/Symbol Tagging
**No explicit stock symbol tags found in RSS or article sample.** Categories are text-based section labels, not ticker symbols. Article titles may **contain symbol names naturally** (e.g., "VNIndex," "VPB"), but no structured `<symbol>` or `<ticker>` metadata present.

### Market Relevance
VnEconomy targets Vietnam domestic market. Coverage includes:
- VNX (HoSE), HNX (Hanoi exchange)
- Company-specific news
- Economic policy & macro trends
- Energy, finance, investment topics

---

## 5. Quirks vs. cafef.vn / vietstock.vn

| Aspect | VnEconomy | cafef.vn | vietstock.vn |
|--------|-----------|----------|--------------|
| **RSS content:encoded** | Empty ❌ | (compare) | (compare) |
| **Image hosting** | `premedia.vneconomy.vn` | (compare) | (compare) |
| **Lazy-load images** | No (direct src) | (compare) | (compare) |
| **Title location** | `<h1>` semantic | (compare) | (compare) |
| **Date format** | "HH:MM, DD/MM/YYYY" (text, not structured) | (compare) | (compare) |
| **Author field** | Text name (sometimes prefix "K") | (compare) | (compare) |
| **Crawl-delay** | 1s (robots.txt) | (compare) | (compare) |
| **JS rendering** | None (server-side) | (compare) | (compare) |

---

## 6. Implementation Readiness

✓ **Ready to implement.** VnEconomy is:
- Server-rendered (no browser automation needed)
- No anti-bot measures
- Consistent feed structure (50 items per feed)
- Accessible detail pages with clear metadata
- robots.txt compliant with 1s crawl-delay

⚠ **Required handling:**
- Skip RSS `<description>` field; must detail-fetch full content
- Parse unstructured date text "HH:MM, DD/MM/YYYY" to ISO 8601
- Handle author prefix parsing (e.g., "K Kim Phong" → ["K", "Kim Phong"])
- Image CDN rewriting if archiving (from `premedia.vneconomy.vn`)

---

## Unresolved Questions

1. **CSS selector for main content body:** Report shows "semantic HTML without specific wrapper class" — need to determine exact container (e.g., `<main>`, `<article>`, or div with implicit role). Recommend manual inspection of 2-3 articles to identify consistent selector.

2. **Article URL structure:** Homepage showed `.htm` extension (e.g., `.mua-ban.htm`), but RSS items may use different patterns. Confirm RSS item URLs match this pattern or detect alternates.

3. **Stock symbol extraction:** No structured ticker tags found. Determine if extraction via NLP (named-entity recognition) on title/body or if VnEconomy provides alternative metadata field.

4. **Duplicate content across cafef/vietstock:** Not yet verified. Recommend cross-checking sample articles (same story published by multiple sources).
