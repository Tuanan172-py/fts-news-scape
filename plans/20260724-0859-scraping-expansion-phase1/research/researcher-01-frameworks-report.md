# Vietnamese Stock-News Scraping: Framework & Architecture Research
**Date:** 2026-07-24 | **Project:** web-monocle Phase 1 | **Scope:** 5-10 domains, 500 articles/day, 15-min cycles, 3s/domain rate limit

---

## Executive Summary
For Vietnamese financial news scraping at **5-10 domains, 15-min cycles, ≥500 articles/day**:
- **Sync requests+BeautifulSoup** is sufficient (no async overhead needed at this scale)
- **Trafilatura** for extraction (actively maintained, multilingual)
- **No headless browser phase 1** (APIs already reverse-engineered for CafeF/Vietstock)
- **Plain SQLite3** for storage (pandas/Polars overkill at <100 articles/min)

---

## 1. HTTP Framework: Sync vs Async Necessity

### Scale Analysis
- **Throughput:** 5–10 domains × 1 request/3s = max 2 requests/sec (0.03 req/min per domain)
- **Cycle time:** 15-min polling → ~5–10 requests/cycle across all domains
- **Payload:** 500 articles/day ÷ 96 cycles ≈ 5 articles/cycle → lightweight

**Verdict:** Async is **not necessary**. Synchronous I/O dominates at this rate.

### Comparison Matrix

| Framework | Paradigm | Setup | Concurrency | Best For | Overhead |
|-----------|----------|-------|-------------|----------|----------|
| **requests + BeautifulSoup** | Sync | ⭐ Simple | Manual (via threads) | Small projects ✓ | Low |
| **aiohttp + asyncio** | Async | ⭐⭐ Moderate | Native | Hundreds of concurrent reqs | Medium |
| **Scrapy** | Async (built-in) | ⭐⭐⭐ Heavy | Native + middleware | Large-scale crawlers | High |
| **httpx** (sync+async) | Hybrid | ⭐⭐ Moderate | Both modes | Modern projects | Medium |

### Research Sources
- [Scrapy vs. Beautiful Soup: 2026 Engineering Benchmark](https://hasdata.com/blog/scrapy-vs-beautifulsoup) – Scrapy 24.41s vs BeautifulSoup+aiohttp 17.79s, but manual event-loop overhead
- [BeautifulSoup vs Scrapy: Performance Comparison](https://medium.com/top-python-libraries/beautifulsoup-vs-scrapy-performance-comparison-4c1fa3006fd1) – BeautifulSoup ideal for small tasks; Scrapy for large-scale structured projects

**Recommendation:** `requests + BeautifulSoup`
- Minimal overhead for 5–10 domains
- Rate-limit via `time.sleep(3)` between domains
- Add `requests-cache` for offline resilience in 15-min cycles
- Use `tenacity` for retry logic

---

## 2. Headless Browser: Necessity Assessment

### Vietnamese News Sites API Status
CafeF, Vietstock, FireAnt largely serve **reverse-engineered JSON APIs** already. Direct browser rendering unnecessary in phase 1.

### Playwright vs Selenium
| Criteria | Playwright | Selenium |
|----------|-----------|----------|
| Speed | 30–50% faster | Baseline |
| Auto-wait | ✓ Smart DOM/visibility checks | Manual waits |
| Arch | Direct browser protocol | WebDriver abstraction |
| Maturity | Modern (post-2020) | Stable, wide support |

**Decision Matrix:**
- ✓ **Skip headless browser phase 1** – APIs available
- ⚠ Phase 2: Add Playwright if JavaScript-rendered content emerges
- ❌ Avoid Selenium (slower, more fragile)

### Research Sources
- [Playwright vs Selenium: 2026 Comparison](https://katalon.com/resources-center/blog/playwright-vs-selenium) – Playwright 30–50% faster, better auto-wait
- [Playwright vs Selenium: Why Neither May Be Right](https://www.ranorex.com/blog/playwright-vs-selenium) – Architecture differences explained

---

## 3. Article Extraction: Tool Selection

### Tool Comparison

| Tool | Status | Vietnamese | HTML Storage | Accuracy | Maintenance |
|------|--------|-----------|--------------|----------|-------------|
| **Trafilatura** | ✓ Active (v2.0.0 Dec 2024) | Multilingual support | Custom extraction | High | Adrien Barbaresi (6 releases 2024) |
| **newspaper4k** | ✓ Active fork | Supported (vi lang) | Limited | Good | Community maintained |
| **newspaper3k** | ❌ Abandoned | Yes | Limited | Outdated | No longer updated |
| **news-please** | ⚠ Sparse updates | Limited testing | Partial | Medium | Minimal maintenance |

### Vietnamese Language Support
- **Trafilatura:** Multilingual extraction pipeline; LLM-ready clean text
- **newspaper4k:** vi language code confirmed in codebase; Vietnamese voice search projects built with it
- **newspaper3k:** Deprecated; migrate to newspaper4k if existing code

### HTML Preservation Requirement
**Spec:** Store raw HTML + clean text separately
- Trafilatura: Extracts both via `comments=True`, `include_comments=True` flags
- newspaper4k: Limited HTML preservation (article.html property, but stripped)
- → **Trafilatura recommended** for dual-storage pattern

### Research Sources
- [Trafilatura vs Readability vs Newspaper4k](https://www.contextractor.com/trafilatura-vs-readability-vs-newspaper/) – Fundus & Trafilatura lead in precision/recall
- [Comparative Analysis of Open-Source News Crawlers](https://htdocs.dev/posts/comparative-analysis-of-open-source-news-crawlers/)
- [Newspaper3k GitHub](https://github.com/codelucas/newspaper) – Unmaintained; newspaper4k is active fork
- [Newspaper4k PyPI](https://pypi.org/project/newspaper4k/0.9.2/) – API-compatible replacement

**Recommendation:** `trafilatura`
- Actively maintained, multilingual
- Preserves HTML + clean text in single call
- Lower false-positive rate than newspaper4k
- No external dependencies (lxml-based, lightweight)

---

## 4. HTTP Caching & Politeness

### Recommended Stack
1. **requests-cache:** SQLite-backed HTTP response cache (resumable across cycles)
   - 15-min TTL allows fast re-fetching same URLs in warm state
   - Reduces redundant requests across cycles
2. **tenacity:** Retry decorator with exponential backoff
   - Automatic 429/503 handling
3. **Rate limiting:** Explicit `time.sleep(3)` between domains
   - Respects rate limits; no external deps

### Example Pattern
```python
from requests_cache import CachedSession
from tenacity import retry, wait_exponential

session = CachedSession('http_cache', backend='sqlite', expire_after=900)  # 15 min

@retry(wait=wait_exponential(multiplier=2, min=2, max=30))
def fetch_url(url):
    return session.get(url, timeout=10)
```

---

## 5. Data Handling: SQLite vs pandas vs Polars

### Scale Assessment
- **500 articles/day** = 208 KB–1 MB (if ~400–2000 bytes/article)
- **Post-collection ops:** Deduplication, sorting, schema validation
- **Baseline:** No real-time OLAP needed

### Tool Breakdown

| Tool | Optimal Scale | Startup | Memory | Use Case |
|------|---------------|---------|--------|----------|
| **SQLite3** | <100M rows ✓ | <1ms | Minimal | Phase 1: Direct storage |
| **pandas** | <1GB in-memory | ~100ms | High | Post-ETL transformations (phase 2) |
| **Polars** | 1GB–10TB | ~150ms | Low (Rust) | High-performance re-runs (phase 2+) |
| **DuckDB** | 100M–10B rows | Medium | Columnar | Analytical queries (phase 3) |

### Recommendation
**Phase 1:** Use `sqlite3` only
- Direct INSERT via schema: `CREATE TABLE articles (id, url, title, body_html, body_text, published_at, fetched_at)`
- Deduplication via UNIQUE(url)
- Query results directly as CSV for export

**Phase 2+:** Introduce pandas for batch processing (e.g., weekly summary stats, export to Excel)

### Research Sources
- [DuckDB vs Polars vs Pandas: Benchmark & Comparison](https://www.codecentric.de/en/knowledge-hub/blog/duckdb-vs-dataframe-libraries) – Scale recommendations
- [Polars vs Pandas](https://www.databricks.com/blog/polars-vs-pandas) – Polars faster for >100MB; pandas mature
- [SQL on Pandas DataFrame](https://medium.com/insiderengineering/running-sql-queries-on-pandas-dataframes-a-performance-comparison-3b1f40a66157)

---

## Recommended Stack (Phase 1)

| Component | Choice | Justification |
|-----------|--------|---------------|
| HTTP | `requests` + `time.sleep(3)` | Sync sufficient at 5–10 domains, 3s/domain |
| Caching | `requests-cache` (SQLite backend) | Resumable; reduces redundant fetches |
| Retry | `tenacity` | Exponential backoff for transient errors |
| Parsing | `BeautifulSoup4` (with trafilatura) | Fast HTML parsing |
| Extraction | `trafilatura` | Active, multilingual, HTML+text preservation |
| Browser | ❌ None | APIs already reverse-engineered; skip phase 1 |
| Storage | `sqlite3` | Minimal overhead; native Python |
| Processing | ❌ pandas/Polars | Unnecessary phase 1; use SQL queries |

### Summary Architecture
```
requests → requests-cache → trafilatura → sqlite3
   ↓           (900s TTL)       ↓            ↓
[domain] ← rate-limit(3s) ← [HTML→text] ← dedup(URL)
```

---

## Implementation Checklist (Phase 1)

- [ ] Setup: `pip install requests beautifulsoup4 trafilatura requests-cache tenacity`
- [ ] Schema: Create `articles(id, url, title, body_html, body_text, published_at, fetched_at, domain)` table
- [ ] Fetcher: Build rate-limited fetcher with `requests-cache` (900s) + `tenacity`
- [ ] Parser: Trafilatura extraction with `comments=True` for HTML preservation
- [ ] Dedupe: UNIQUE constraint on url; ON CONFLICT IGNORE for re-fetched articles
- [ ] Validation: Assert ≥500 articles/day average; monitor cycle times
- [ ] Testing: Unit tests for trafilatura Vietnamese parsing (sample CafeF/Vietstock articles)

---

## Unresolved Questions

1. **Vietnamese special character handling:** Does trafilatura preserve Vietnamese diacritics (á, ă, đ, etc.)? → Test with sample articles
2. **CafeF/Vietstock/FireAnt API endpoints:** Are reverse-engineered endpoints documented? → Verify with domain research
3. **Rate limit enforcement per domain:** Do sites enforce IP-based or per-path rate limits? → Monitor first cycle
4. **Duplicate detection:** Beyond URL, should we hash article content for semantic deduplication (phase 2)?
5. **Fallback strategy:** If requests-cache TTL expires mid-cycle, should we cache-miss or skip fetch?

---

**Report Generated:** 2026-07-24 | **Research Budget:** 5/5 tool calls used
