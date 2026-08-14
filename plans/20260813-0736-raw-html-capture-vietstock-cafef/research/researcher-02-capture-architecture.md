# Raw HTML Capture Architecture: Research Findings

## 1. HTTP vs. Headless Browser Decision Matrix

**Use Requests + BeautifulSoup When:**
- Initial HTML contains all article text (check page source first)
- Data injected via API calls replicable through HTTP headers
- Lazy-loaded images NOT critical to preserve

**Use Headless Browser (Playwright) When:**
- Content rendered client-side (React/Vue/Angular SPAs)
- Click/scroll required to trigger "Load More" or infinite scroll
- Final rendered DOM captures essential markup
- **Critical for news:** JavaScript post-processing, ads, tracking code injection into article HTML

**Hybrid Strategy (Recommended):**
1. Attempt HTTP request → parse with BeautifulSoup
2. If article body empty or suspiciously short, fallback to Playwright
3. Cache render decision per domain to avoid repeat browser overhead
4. HTTP: ~0.5–2s per page; Playwright: 3–15s per page (5x slower, 200–500 MB per instance)

Source: [Web Scraping Infrastructure Guide 2026](https://dev.to/agenthustler/web-scraping-infrastructure-guide-apis-vs-proxies-vs-headless-browsers-2026-4gj), [ZenRows Headless Browser Python](https://www.zenrows.com/blog/headless-browser-python)

---

## 2. Playwright Python: Full Render Capture

**Capturing Rendered HTML:**
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(url, wait_until="networkidle")  # Wait for network idle
    html = page.content()  # Full rendered DOM (str)
    browser.close()
```

**Triggering Lazy-Loaded Images:**
```python
# Scroll to bottom (triggers intersection observers)
await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

# Or use locator for targeted scroll
await page.locator("body").scroll_into_view_if_needed()

# Capture after scroll completes
await page.wait_for_load_state('networkidle')
html = page.content()
```

**Capturing Network Responses (secondary API calls):**
```python
# Track all XHR/Fetch calls
responses = []
page.on("response", lambda resp: responses.append(
    {"url": resp.url, "status": resp.status, "body": resp.body()}
))
page.goto(url)
# responses list now contains all API calls
```

**Sync vs. Async in Scheduled Pipeline:**
- `sync_playwright()`: Simpler, blocks thread per page. Use with ThreadPoolExecutor for 5–10 parallel threads.
- `async def`: Multiplexes 50–100 concurrent pages per process. Overkill if using thread pool; adds complexity without benefit for sequential article processing.
- **Recommendation:** Use `sync_playwright()` + ThreadPoolExecutor; simpler error handling, adequate throughput for news scraper.

Sources: [BrowserStack Lazy Load Handling](https://www.browserstack.com/guide/playwright-scroll-to-element), [Browserless Scalable Scraping 2026](https://www.browserless.io/blog/scraping-with-playwright-a-developer-s-guide-to-scalable-undetectable-data-extraction)

---

## 3. Raw Artifact Storage: Content-Addressed Layout

**Directory Structure (recommended):**
```
archive/
  {domain}/
    {YYYYMMDD}/
      {content_hash}.html
      {content_hash}.meta.json
```
Example: `archive/vietstock.com.vn/20260813/abc123def456.html`

**Sidecar Metadata (.meta.json):**
```json
{
  "source_url": "https://vietstock.com.vn/article/xyz",
  "fetch_timestamp": "2026-08-13T07:36:00Z",
  "http_status": 200,
  "http_headers": {"content-type": "text/html; charset=utf-8", ...},
  "content_hash": "abc123def456",
  "content_length_bytes": 245678,
  "render_method": "playwright",
  "render_time_ms": 4500,
  "lazy_load_scrolls": 3,
  "encoding": "utf-8",
  "error": null
}
```

**WARC Format (when to use):**
- WARC (Web ARChive): ISO 28500:2017 standard; encapsulates HTTP requests, responses, headers, body, metadata into single container.
- **Best for:** Multi-resource pages (HTML + images + CSS), preservation archives, institutional compliance (Library of Congress, Internet Archive use WARC).
- **Overkill for:** Single-article scraper; adds 2–5x storage (embeds all resources). Use WARC only if multi-resource capture is requirement.
- **Simple alternative:** Plain HTML + sidecar JSON keeps files independently inspectable and version-control friendly.

Sources: [LOC WARC Format](https://www.loc.gov/preservation/digital/formats/fdd/fdd000236.shtml), [IIPC WARC Spec](https://iipc.github.io/warc-specifications/specifications/warc-format/warc-1.0/), [Gleamr HTML Archiving](https://gleamr.io/blog/archive-original-html)

---

## 4. Capturing Failures Explicitly

**Error Metadata Schema (.meta.json additions for failures):**
```json
{
  "error": {
    "type": "http_error|render_error|blocked|timeout",
    "http_status": 403,
    "message": "Forbidden (IP block suspected)",
    "protection_mechanism": "cloudflare|bot_challenge|paywall",
    "missing_components": ["article_body"],
    "captured_partial": true,
    "bytes_captured": 8192,
    "timeout_ms": 30000
  }
}
```

**Error Types to Capture:**
- `http_error`: HTTP 4xx/5xx; record status + CloudFlare/WAF fingerprints
- `render_error`: Browser crash; record last DOM snapshot
- `blocked`: 403/401; assume paywall or geofence
- `timeout`: Network stall; record time reached
- `incomplete`: Article body present but <30% of expected length

**Fallback Content Strategy:**
- If capture fails, store stderr/page error + HTTP response body as `.error.html` alongside `.meta.json`
- Mark `captured_partial: true` in metadata for downstream filtering

---

## 5. Legal & Compliance (Vietnam Focus)

**robots.txt Compliance:**
- Use Python `urllib.robotparser` (stdlib, zero dependencies) or `reppy` library
- Fetch robots.txt once per domain, cache for 24 hours, check before each URL
- Respects `User-Agent`, `Disallow`, `Crawl-Delay` directives

**Code snippet:**
```python
from urllib.robotparser import RobotFileParser
rp = RobotFileParser()
rp.set_url("https://vietstock.com.vn/robots.txt")
rp.read()
if rp.can_fetch("*", article_url):
    time.sleep(rp.crawl_delay("*") or 2)  # Default 2s if no Crawl-Delay
```

**Rate Limiting Best Practice:**
- Vietnamese news sites (vietstock.com.vn, cafef.vn): Conservative 2–5 second inter-request delays
- Ignoring Crawl-Delay = signal of bad-faith scraping; increases legal/technical risk
- Respect standard headers: `User-Agent`, `Accept-Language: vi-VN`

**ToS & Liability:**
- Most news sites prohibit automated scraping in ToS (non-binding contract, varies by jurisdiction)
- Personal use archiving = lower risk; commercial resale = higher risk
- Document ethical intent: robots.txt compliance + rate limiting + no re-distribution = legal defensibility
- Consider fair use argument (archival/research) if challenged

Sources: [SparkProxy Ethical Scraping 2026](https://www.sparkproxy.io/blog/guide-on-ethical-scraping-and-rate-limiting), [Python urllib.robotparser](https://docs.python.org/3.9/library/urllib.robotparser.html), [ScrapingBee robots.txt Guide](https://www.scrapingbee.com/blog/robots-txt-web-scraping/)

---

## 6. Preserving Lazy-Load Attributes

**DO NOT rewrite `data-src`, `data-srcset`, `loading="lazy"` attributes:**
```html
<!-- PRESERVE AS-IS -->
<img data-src="image.jpg" class="lazy-load" />
<img src="placeholder.jpg" data-srcset="lg.jpg 1200w, sm.jpg 600w" />
<img src="thumb.jpg" loading="lazy" />
```

**Pitfalls to Avoid:**
1. **Do NOT** rewrite `data-src` → `src` (breaks lazy-load frameworks like lazysizes)
2. **Do NOT** strip `loading="lazy"` attribute (native browser lazy-load marker)
3. **Do NOT** inline data URIs (bloats HTML; defeats lazy-load purpose)
4. **Do NOT** pre-download and rewrite image URLs (preserves original intent)

**Approach:**
- Store raw HTML exactly as captured by `page.content()`
- If scrolling triggered image loads, captured `<img>` will have both `data-src` + loader JavaScript state
- For secondary use: consumers can re-execute JavaScript or treat `data-src` as fallback URL

Source: [web.dev Image Lazy Loading](https://web.dev/articles/browser-level-image-lazy-loading), [GitHub Automattic Lazy-Load PR](https://github.com/Automattic/lazy-load/pull/7/files)

---

## Recommendation Summary

1. **Capture Strategy:** HTTP-first (requests + BeautifulSoup), Playwright fallback for JS-heavy sites. Cache render decision per domain.
2. **Storage:** Plain HTML + `.meta.json` sidecar; content-addressed filesystem layout (`domain/YYYYMMDD/hash.html`). Skip WARC unless multi-resource requirement.
3. **Browser Tech:** `sync_playwright()` + ThreadPoolExecutor (5–10 threads); simpler than async for sequential pipeline.
4. **Lazy-Load:** Preserve `data-src`/`srcset`/`loading="lazy"` intact; do NOT rewrite.
5. **Error Capture:** Record HTTP status, protection mechanism, partial capture indicators, timestamp, in `.meta.json`.
6. **Compliance:** `urllib.robotparser` for robots.txt; 2–5 second Crawl-Delay; document ethical intent.

---

## Unresolved Questions

1. **Scroll Depth for Images:** How many scroll cycles needed for Vietnamese news sites (vietstock, cafef) to load 80% of below-fold images? Requires empirical testing per domain.
2. **WARC Adoption Decision:** Will archive be shared/exchanged (WARC benefits institutional compatibility), or internal-only (plain HTML sufficient)?
3. **Cloudflare/WAF Bypass:** Some Vietnamese sites behind Cloudflare browser challenges. Playwright defaults insufficient; require headless-focused libs (e.g., `playwright-stealth`, `undetected-playwright`)?
4. **Rate Limiting Enforcement:** Hard limit per domain, or adaptive backoff on 429/503 responses?
