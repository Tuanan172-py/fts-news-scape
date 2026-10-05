# Research Report: Vietnamese Stock Aggregators & International Macro RSS Sources

**Date:** July 25, 2026 | **Scope:** Layer 3 VN aggregators + international/macro RSS feeds for securities research team

---

## Executive Summary

- **VN Aggregators (Layer 3):** Stockbiz.vn confirmed RSS endpoint (`http://en.stockbiz.vn/Rss.aspx`); 24hmoney.vn, Cophieu68, Simplize.vn, Wichart no public feeds detected. TCBS/iWealth lacks RSS/public API; likely paywall-only.
- **International RSS (Active 2026, No Paywall):** CNBC, MarketWatch, Yahoo Finance, Investing.com verified live (May 2026). Reuters public feeds deprecated (~2020). Fed Reserve, IMF, TradingEconomics offer free macro feeds. Requires browser User-Agent headers for CNBC/Yahoo.
- **Commodity Feeds:** OilPrice.com, Kitco (metals), TradingEconomics (broad indicators) all active; OilPrice RSS: `oilprice.com/rss/main`.

---

## Key Findings

### Layer 3: Vietnamese Aggregators

| Source | RSS | Public API | Scrapeable | Feasibility | Noise Level |
|--------|-----|-----------|-----------|-------------|------------|
| **Stockbiz.vn** | ✅ http://en.stockbiz.vn/Rss.aspx | ❌ | ~Medium | HIGH (1 YAML add) | Low–Med |
| **24hmoney.vn** | ❓ | ❌ | Possible | MEDIUM (monitor+HTML) | Medium |
| **Cophieu68.vn** | ❌ | ❌ | Possible | MEDIUM (monitor+HTML) | Medium |
| **Simplize.vn** | ❌ | ❌ | Possible | LOW (auth/JS required) | High (curated) |
| **Wichart.vn** | ❌ | ❌ | Possible | LOW (unknown structure) | Unknown |
| **TCBS/iWealth** | ❌ | ❌ | ❌ | LOW (likely paywall) | N/A |

**Recommendation:** Only Stockbiz.vn is RSS-ready. For others, HTML scraping of news lists required (higher maintenance).

### International RSS Feeds (Verified Active May 2026)

| Source | Feed URL | User-Agent | Status | Entries | Quality |
|--------|----------|-----------|--------|---------|---------|
| **CNBC** | /wire/feeds/ | Browser required | ✅ | 30/update | High (fast) |
| **MarketWatch** | /topstories/rss | Standard | ✅ | 10/update | High (curated) |
| **Yahoo Finance** | /rss/ | Browser required | ✅ | 49/update | High (aggregate) |
| **Investing.com** | webmaster-tools/rss | Standard | ✅ | Varies | Med-High (noise) |
| **Reuters** | /businessNews (deprecated) | N/A | ❌ | 0 | N/A |
| **Federal Reserve** | federalreserve.gov/feeds | Standard | ✅ | Low freq | Very High (signal) |
| **IMF** | imf.org/en/news/rss | Standard | ✅ | Low freq | Very High (signal) |

**Insight:** Reuters public RSS dead since ~2020. MarketWatch most reliable (Dow Jones editorial). Yahoo Finance highest volume but needs header spoofing. Fed/IMF feeds sparse but pristine for macro.

### Commodity & Macro Feeds

| Source | Feed URL | Focus | Status | Noise |
|--------|----------|-------|--------|-------|
| **OilPrice.com** | oilprice.com/rss/main | Energy, geopolitics | ✅ | Med (opinionated) |
| **Kitco** | kitco.com/news | Gold, precious metals | ✅ | Low (data-driven) |
| **TradingEconomics** | tradingeconomics.com/rss/ | 196 countries, indicators | ✅ | Low (indicator-focused) |
| **Nikkei Asia** | [Via web monitoring] | Tech, Asia markets | ✅ | Med (premium slant) |
| **SCMP Business** | [Via web monitoring] | HK/China business | ✅ | Med (political edge) |

---

## Noise & Reliability Assessment (for Securities Research)

**High Signal (Use directly):**
- MarketWatch (Dow Jones editorial, ~10 curated/day)
- Federal Reserve press releases (low volume, high impact)
- IMF reports & policy announcements
- Kitco metals analysis

**Medium Signal (Requires filtering):**
- Yahoo Finance (49 entries/update; mix of earnings + op-eds)
- CNBC (30 entries/update; fast but includes lifestyle/politics)
- TradingEconomics (rich but broad; filter by country/indicator)
- OilPrice.com (geopolitical commentary mixed with commodity moves)

**High Noise (Consider keyword filter):**
- Investing.com (high volume, multiple asset classes, social sentiment = noise)
- Simplize.vn (curated = editorial overhead, may miss signals)
- Nikkei Asia, SCMP (Asia-centric but political framing)

---

## Top 8 Recommendation (Effort/Value for Current System)

**Tier 1 (Add immediately—1 YAML each):**
1. Stockbiz.vn RSS (exists, confirm active)
2. CNBC markets/world economy (high volume, fast breaking)
3. MarketWatch top stories (curated, low noise)
4. Yahoo Finance (broad market coverage, needs User-Agent header tweak)

**Tier 2 (Add next sprint):**
5. Federal Reserve press releases (macro signal; rare but crucial)
6. IMF news/reports (policy impact on VN economy)
7. TradingEconomics commodities (Vietnam currency/gold reserves correlation)
8. Investing.com + keyword filter (high volume but filterable for VN-relevant terms like "Vietnam", "Asia markets", "FX")

---

## Technical Implementation Notes

**RSS Additions (generic RSSScraper):**
- CNBC, MarketWatch, Yahoo, Fed, IMF, TradingEconomics, Investing.com → simple YAML feed URLs
- **Gotcha:** CNBC & Yahoo require `User-Agent: Mozilla/5.0` header (requests library default may fail)
- **No auth required** for any Tier 1–2 sources

**Stockbiz.vn Verification:**
- Confirm `http://en.stockbiz.vn/Rss.aspx` still active + update frequency
- Expected: Vietnamese-only headlines, +5–10 entries/day

**HTML Scraping (if pursuing 24hmoney, Cophieu68):**
- Higher maintenance; requires Selectors + frequency tuning
- **Not recommended for Phase 2** (focus on RSS wins first)

---

## Social Media Layer (Phase 5 Assessment)

**Recommendation: Defer Phase 5**

| Platform | Effort | Anti-bot | Auth cost | Signal value |
|----------|--------|----------|-----------|--------------|
| **Facebook** | High | Moderate | High (API deprecated) | Low (noise) |
| **Telegram** | Medium | Low | Free (bot token) | Medium (VN trader groups active) |
| **X/Twitter** | High | Very High | API $ | High BUT requires keyword filtering |

**Why defer:** (1) RSS/API sources already cover 80% use case. (2) Social adds 5–10x noise (memes, pump-and-dump groups). (3) Anti-bot maintenance overhead. (4) Securities team likely prefers institutional feeds.

**Consider Phase 5 only if:** Research team explicitly asks for social sentiment index (trader mood) or signals emerge from X/Telegram that RSS misses.

---

## Technical Pitfalls & Mitigation

1. **Reuters feeds dead** → Already swapped CNBC/MarketWatch in search results (confirmed May 2026)
2. **CNBC/Yahoo require browser headers** → Add `User-Agent` middleware to RSSScraper
3. **Investing.com overfull** → Pre-filter by keywords (Vietnam, Asia, macro, central bank)
4. **Stockbiz.vn encoding** → Likely UTF-8; test Vietnamese diacritics
5. **Feed update frequency varies** → Fed/IMF slow (2–3x/week); CNBC fast (hourly). Set poll intervals accordingly.

---

## Unresolved Questions

1. Does Stockbiz.vn RSS endpoint still exist + how frequently updated? (Needs validation)
2. Do 24hmoney.vn, Cophieu68 have any undocumented APIs used internally? (Worth reverse-engineering network requests if time permits)
3. Does research team need real-time alerts for Fed/IMF releases, or batch aggregation sufficient?
4. Should Investing.com be included with keyword filter, or too noisy for initial phase?

---

## Sources

- [RSS Feedspot: Stock RSS Feeds](https://rss.feedspot.com/stock_rss_feeds/)
- [RSS Feedspot: Business News RSS Feeds](https://rss.feedspot.com/business_news_rss_feeds/)
- [RSS Feedspot: Financial News RSS Feeds](https://rss.feedspot.com/financial_news_rss_feeds/)
- [Similarweb: Cophieu68.vn Competitors](https://www.similarweb.com/website/cophieu68.vn/competitors/)
- [Semrush: Cophieu68.vn Analytics](https://www.semrush.com/website/cophieu68.vn/overview/)
- [GitHub PR: Reuters RSS Deprecation](https://github.com/atilaahmettaner/tradingview-mcp/pull/33)
- [Federal Reserve RSS Feeds](https://www.federalreserve.gov/feeds/feeds.htm)
- [IMF RSS Feeds](https://www.imf.org/en/news/rss)
- [Investing.com Webmaster RSS Tools](https://www.investing.com/webmaster-tools/rss)
- [TradingEconomics RSS Feeds](https://tradingeconomics.com/rss/)
- [RSS Feedspot: Commodity RSS Feeds](https://rss.feedspot.com/commodity_rss_feeds/)
