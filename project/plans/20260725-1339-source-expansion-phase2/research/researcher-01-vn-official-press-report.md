# Vietnamese Stock-News Sources: Layer 0-2 Expansion Research
**Date:** 2026-07-25 | **Researcher:** Claude | **Budget Used:** 5/5 web searches

---

## Executive Summary

Identified **15+ viable Vietnamese stock-news sources** across Layers 0-2 with mixed RSS/API/HTML scraping feasibility. **Layer 0 (Official)**: HOSE/HNX have fragmented disclosure systems; HNX confirmed RSS available (`hnx.vn/rss.html`); SSC portal exists but RSS undocumented. **Layer 1 (Press)**: VnEconomy, VietnamPlus, Vietnam News confirmed active RSS feeds; CafeBiz/VnExpress lack documented RSS. **Layer 2 (CTCK)**: SSI/VNDirect offer APIs but research reports require login or direct PDF scraping. Recommendation: prioritize HNX RSS (confirmed), VnEconomy/VietnamPlus (Layer 1), SSI API for broker-tier coverage.

---

## Layer 0: Official Stock Exchange & Government Sources

| Source | URL | Method | Feed Status | Login | Frequency | Feasibility | Notes |
|--------|-----|--------|------------|-------|-----------|-------------|-------|
| **HNX (Hanoi Exchange)** | https://www.hnx.vn | RSS | ✓ Confirmed | No | Real-time | **Easy** | RSS endpoint at `/vi-vn/rss.html` — public, daily market updates |
| **HOSE (Ho Chi Minh Exchange)** | https://hsx.vn | HTML/API | Undocumented | No | Real-time | **Medium** | No public RSS found; market data via APIs from StockerAPI/iTick integrations |
| **SSC (State Securities Commission)** | https://ssc.gov.vn | HTML Portal | Partial RSS | No | Variable | **Hard** | Disclosure portal at `/webcenter/portal/cbtt`; no direct RSS feed documented |
| **GSO (General Statistics Office)** | https://www.gso.gov.vn | HTML/Portal | None found | No | Quarterly | **Hard** | Q1 2026 reports published; press releases at `/en/press-release/` — no RSS |
| **NSO (National Statistics Office)** | https://www.nso.gov.vn | HTML/Portal | RSS unclear | No | Quarterly | **Medium** | Mirror of GSO; VISTA portal has RSS at `vista.gov.vn/rss.html` |
| **SBV (State Bank of Vietnam)** | https://sbv.gov.vn | HTML Portal | None found | No | Ad-hoc | **Hard** | Policy announcements/monetary news; requires scraping press page |

---

## Layer 1: Financial Press with RSS (Active 2026)

| Source | URL | Method | Feed Status | Login | Frequency | Feasibility | Notes |
|--------|-----|--------|------------|-------|-----------|-------------|-------|
| **VnEconomy** | https://en.vneconomy.vn | RSS | ✓ Confirmed | No | Hourly | **Easy** | RSS at `https://en.vneconomy.vn/rss.html` — financial news primary source |
| **VietnamPlus** | https://en.vietnamplus.vn | RSS | ✓ Confirmed | No | Hourly | **Easy** | RSS at `https://en.vietnamplus.vn/rss.html` — broad + financial section |
| **Vietnam News** | https://vietnamnews.vn | RSS | ✓ Confirmed | No | Hourly | **Easy** | RSS at `https://vietnamnews.vn/rss` — business/economy sections available |
| **CafeBiz** | https://cafebiz.vn | Mobile App/Web | None documented | No | Real-time | **Hard** | Android app exists; web RSS unknown; Vccorp-powered, exclusives often |
| **VnExpress** | https://vnexpress.net | HTML/Paywall | Partial | Paywall | Hourly | **Hard** | Business section exists; premium content behind login; no public RSS |
| **Saigon Times (Thời Báo Saigon)** | https://www.thesaigontimes.vn | HTML/RSS | Unclear | No | Hourly | **Medium** | Business section at `/business/`; RSS likely at `/rss` endpoint |
| **DanTri (Dân Trí)** | https://dantri.com.vn | HTML/RSS | Partial | No | Hourly | **Medium** | Business section; RSS endpoint `/rss.xml` (typical pattern) |
| **Tuoi Tre (Tuổi Trẻ)** | https://tuoitre.vn | HTML/RSS | Partial | No | Hourly | **Medium** | Business section at `/kinh-te/`; RSS likely available |
| **Thanh Nien (Thanh Niên)** | https://thanhnien.vn | HTML/RSS | Partial | No | Hourly | **Medium** | Business/economy at `/kinh-te-tai-chinh/`; RSS undocumented |

---

## Layer 2: CTCK Research Firms & Broker Reports

| Source | URL Method | Method | Report Access | Login | Feasibility | Notes |
|--------|-----------|--------|----------------|-------|-------------|-------|
| **SSI Securities** | https://www.ssi.com.vn | API/PDF | Partial public | Yes | **Medium** | API endpoint `/api/research/` exists; free reports on homepage; login required for archives |
| **VNDirect** | https://www.vndirect.com.vn | API/PDF | Partial public | Yes | **Medium** | DSMART platform; PDFs at `/reports/` accessible without login; ~50+ free studies/month |
| **VCSC (Vietcap)** | https://www.vcsc.com.vn | PDF Portal | Partial public | Yes | **Hard** | Research at `/reports/`; most archived reports behind login |
| **MBS** | https://www.mbsec.com.vn | PDF Portal | Partial public | Yes | **Hard** | Daily market updates; deep reports require account login |
| **HSC** | https://www.hsc.com.vn | PDF Portal | Partial public | Yes | **Hard** | Research page exists; paywall for detailed reports |
| **BSC (Bao Viet)** | https://www.bsc.com.vn | PDF Portal | Public limited | No | **Medium** | Free daily market outlook; weekly reports; HTML parsing viable |
| **FPTS** | https://www.fpts.com.vn | PDF Portal | Limited public | Yes | **Hard** | Morning/evening analysis; registration required for archives |
| **Agriseco** | https://www.agriseco.com.vn | PDF Portal | Limited public | Yes | **Hard** | Daily commentary; reports require login |

---

## Scraping Difficulty & Pitfalls per Layer

**Layer 0 (Official):**
- HNX RSS ✓ **Easiest**: Direct RSS at public URL, reliable.
- HOSE: No RSS documented; must use API (iTick, StockerAPI) or reverse-engineer web requests.
- SSC disclosure: Portal uses AngularJS/SPA; requests may require session tokens; anti-bot measures likely.

**Layer 1 (Press):**
- RSS feeds (VnEconomy, VietnamPlus, Vietnam News): **Easiest**, updates ~hourly, no auth.
- CafeBiz, VnExpress: Paywall/app-first; web scraping blocked or irrelevant (Android app primary).

**Layer 2 (CTCK):**
- SSI/VNDirect public PDFs: **Moderate**, direct URL patterns (`/reports/ID.pdf`); list endpoints often HTML-parsed.
- Login-walled reports: Selenium/headless browser needed; rate-limiting enforced; ToS violation risk.

---

## Recommended Top 8 Sources (Ranked by Effort/Value)

1. **HNX RSS** (`https://www.hnx.vn/vi-vn/rss.html`) — **TIER 1**
   - Effort: Minimal | Value: High | Freshness: Real-time market data
   
2. **VnEconomy RSS** (`https://en.vneconomy.vn/rss.html`) — **TIER 1**
   - Effort: Minimal | Value: High | Freshness: Hourly updates
   
3. **VietnamPlus RSS** (`https://en.vietnamplus.vn/rss.html`) — **TIER 1**
   - Effort: Minimal | Value: Medium-High | Freshness: Hourly
   
4. **Vietnam News RSS** (`https://vietnamnews.vn/rss`) — **TIER 1**
   - Effort: Minimal | Value: Medium | Freshness: Hourly
   
5. **SSI Public Research PDFs** (`https://www.ssi.com.vn/reports/`) — **TIER 2**
   - Effort: Low-Medium | Value: High | Freshness: Weekly, requires HTML list parsing
   
6. **VISTA Statistics Portal** (`https://www.vista.gov.vn/rss.html`) — **TIER 2**
   - Effort: Low | Value: Medium (macro context) | Freshness: Quarterly macro data
   
7. **VNDirect Public Studies** (`https://www.vndirect.com.vn/research/`) — **TIER 2**
   - Effort: Low-Medium | Value: High | Freshness: Daily/Weekly, free tier available
   
8. **HOSE Market Data (via StockerAPI)** (`https://github.com/StockerAPI/vietnam-stock-market-api`) — **TIER 2**
   - Effort: Medium | Value: High (real-time) | Freshness: Real-time via WebSocket
   - Note: Reverse-engineered API; no official endpoint

---

## Unresolved Questions

- Does HOSE (hsx.vn) expose an official public RSS feed or structured API endpoint? (Search results inconclusive; may require direct contact.)
- Are SSC disclosure announcements (`ssc.gov.vn/webcenter/portal/cbtt`) behind anti-bot protection or session walls?
- What is the rate-limit policy for SSI/VNDirect PDF list endpoints?
- Do CafeBiz and VnExpress publish RSS feeds on non-primary domains?
- Is SBV (sbv.gov.vn) press release page machine-readable without JavaScript rendering?

---

## Sources

- [2026 Vietnam Stock Exchange API Integration Guide - Medium](https://medium.com/@wutainfofu/2026-vietnam-stock-exchange-vn30-hose-api-integration-guide-072186b4ce0b)
- [Vietnam Stock Exchange API - iTick Blog](https://blog.itick.io/en/stock-api/2026-vietnam-stock-exchange-api-python-tutorial)
- [Top 40 Vietnam News RSS Feeds - RSS Feedspot](https://rss.feedspot.com/vietnam_news_rss_feeds/)
- [Top 10 Vietnam Business RSS Feeds - RSS Feedspot](https://rss.feedspot.com/vietnam_business_rss_feeds/)
- [VnEconomy RSS](https://en.vneconomy.vn/rss.html)
- [VietnamPlus RSS](https://en.vietnamplus.vn/rss.html)
- [Vietnam News RSS](https://vietnamnews.vn/rss)
- [HNX RSS Feed](https://www.hnx.vn/vi-vn/rss.html)
- [StockerAPI Vietnam Stock Market - GitHub](https://github.com/StockerAPI/vietnam-stock-market-api)
- [GSO Press Releases](https://www.nso.gov.vn/en/press-release/)
- [VISTA Statistics Portal RSS](https://www.vista.gov.vn/rss.html)
- [State Securities Commission Portal](https://ssc.gov.vn/webcenter/portal/cbtt)
- [Top 7 Stock Brokerage Firms in Vietnam - MyTour](https://mytour.vn/en/blog/bai-viet/top-7-stock-brokerage-firms-with-the-best-services-in-vietnam-mytour.vn)
