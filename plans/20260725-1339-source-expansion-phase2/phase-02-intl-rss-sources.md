# Phase 2 (Sprint B): International RSS Sources ×5 (6 feeds)

## Context links

- Plan overview: [plan.md](plan.md)
- Verification report (source of truth): [reports/01-live-verification-report.md](reports/01-live-verification-report.md)
- Features phụ thuộc (language, filter, BOM): [phase-03-filter-encoding-features.md](phase-03-filter-encoding-features.md)
- Research context: [research/researcher-02-aggregator-intl-report.md](research/researcher-02-aggregator-intl-report.md) (Reuters chết, Stockbiz chết — đã verify)
- Generic scraper: `src/scrapers/rss_generic.py`

## Overview

- **Date:** 2026-07-25
- **Description:** Add 5 nguồn quốc tế / 6 feeds bằng YAML: CNBC (×2 feeds), MarketWatch,
  Yahoo Finance, Federal Reserve, OilPrice. Tiếng Anh → `language: en`, sentiment
  neutral by design. Tối ưu cycle-time: hạn chế detail fetch cho nguồn EN.
- **Priority:** MEDIUM (sau Phase 3 + có thể sau Batch 1 Phase 1)
- **Implementation status:** Not started
- **Review status:** Not reviewed

## Key Insights

- 6 feeds verified working 2026-07-25 với item counts thật. Researcher-02 Tier-1 rec
  Stockbiz **chết** (empty response); Reuters public RSS chết từ ~2020; Investing.com
  blocked; Kitco không có RSS — tất cả OUT.
- CNBC cần browser User-Agent — `HTTPClient` đã có UA rotation Mozilla → không cần code.
- Fed feed có BOM → cần `_decode_feed` (Phase 3). Macro signal rất cao, tần suất thấp.
- CNBC Top News noise cao (lifestyle/politics) → keyword filter EN.
- Sentiment VN không áp dụng EN → orchestrator gán neutral (Phase 3). Chấp nhận Phase 2.
- Detail fetch trang EN rủi ro cao (consent walls Yahoo, paywall MarketWatch) + tốn
  cycle time → mặc định `extract_full: false` cho Yahoo/MarketWatch/CNBC (summary đủ
  cho signal scanning); Fed + OilPrice thử `extract_full: true` cap thấp (volume nhỏ).

## Requirements

- 5 YAML mới, tất cả có `language: en`.
- CNBC Top News có `filter.any` EN keywords.
- Cycle-time budget: 5 domain EN thêm ≤2 phút steady-state (ít detail fetch).
- Quality gate: EN articles có title+date+summary (body = summary chấp nhận được khi
  `extract_full: false` — ghi chú trong success criteria).

## Architecture

Không đổi — generic RSSScraper + config. `language: en` chảy qua metadata →
orchestrator skip sentiment (Phase 3). Classifier rule-based VN không match EN → chỉ
có category = feed name (chấp nhận).

## Related code files

**Create (5 YAML):**
- `config/domains/cnbc.yaml`
- `config/domains/marketwatch.yaml`
- `config/domains/yahoofinance.yaml`
- `config/domains/fed.yaml`
- `config/domains/oilprice.yaml`

**Modify:**
- `docs/skills/rss-sources.md` — section "Nguồn quốc tế" mới.
- `README.md` — bảng nguồn tin.

**Delete:** none.

## Implementation Steps

1. `config/domains/cnbc.yaml`:
   ```yaml
   name: cnbc
   enabled: true
   method: rss
   language: en
   rate_limit: 3.0
   timeout: 30
   rss:
     feeds:
       - {url: "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258", name: "CNBC World Economy"}
       - {url: "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", name: "CNBC Top News"}
   filter:
     any: ["stock", "market", "fed", "inflation", "rate", "earnings", "economy",
           "oil", "gold", "treasury", "bond", "china", "asia", "tariff", "gdp",
           "central bank", "currency", "vietnam"]
     drop_unmatched: true
   detail: {extract_full: false, max_details_per_cycle: 0}
   pitfalls: "Cần browser UA (HTTPClient sẵn có). Top News noise cao → filter. 30+30 items. Verified 2026-07-25."
   ```
   Lưu ý: filter per-domain → áp cả World Economy feed; keyword list rộng nên
   World Economy items gần như đều match (chấp nhận, KISS).

2. `config/domains/marketwatch.yaml`:
   ```yaml
   name: marketwatch
   enabled: true
   method: rss
   language: en
   rate_limit: 3.0
   timeout: 30
   rss:
     feeds:
       - {url: "https://feeds.content.dowjones.io/public/rss/mw_topstories", name: "MarketWatch Top Stories"}
   detail: {extract_full: false, max_details_per_cycle: 0}
   pitfalls: "Curated 10 items, noise thấp, không cần filter. Detail = paywall Dow Jones → summary-only. Verified 2026-07-25."
   ```

3. `config/domains/yahoofinance.yaml`:
   ```yaml
   name: yahoofinance
   enabled: true
   method: rss
   language: en
   rate_limit: 3.0
   timeout: 30
   rss:
     feeds:
       - {url: "https://finance.yahoo.com/news/rssindex", name: "Yahoo Finance News"}
   detail: {extract_full: false, max_details_per_cycle: 0}
   pitfalls: "42 items. Detail page có consent wall → summary-only. Cần browser UA (sẵn có). Verified 2026-07-25."
   ```

4. `config/domains/fed.yaml`:
   ```yaml
   name: fed
   enabled: true
   method: rss
   language: en
   rate_limit: 3.0
   timeout: 30
   rss:
     feeds:
       - {url: "https://www.federalreserve.gov/feeds/press_all.xml", name: "Federal Reserve Press"}
   detail: {extract_full: true, max_details_per_cycle: 10}
   pitfalls: "BOM trước <?xml — cần _decode_feed (Phase 3). 20 items, tần suất thấp, signal macro rất cao. Full text đáng lấy (press release ngắn, gov site không chặn). Verified 2026-07-25."
   ```

5. `config/domains/oilprice.yaml`:
   ```yaml
   name: oilprice
   enabled: true
   method: rss
   language: en
   rate_limit: 3.0
   timeout: 30
   rss:
     feeds:
       - {url: "https://oilprice.com/rss/main", name: "OilPrice Main"}
   detail: {extract_full: true, max_details_per_cycle: 10}
   pitfalls: "15 items, commodity/energy. Nếu detail fetch bị chặn/chậm → hạ extract_full: false. Verified 2026-07-25."
   ```

6. **Smoke test:** `python scripts/run_once.py cnbc marketwatch yahoofinance fed oilprice`
   — check: fetched counts ≈ verification (30/30/10/42/20/15), sentiment = neutral
   toàn bộ, metadata.language = "en" (sqlite spot-check), Fed BOM parse OK.

7. **Cycle-time đo:** ghi duration 5 domains; mục tiêu ≤2 phút steady-state
   (chỉ feed fetch + Fed/OilPrice ≤10 details). Nếu vượt → Fed/OilPrice
   `extract_full: false`.

8. **Dedup EN:** fuzzy dedup so trong cross-domain pool — EN titles không đụng VN titles
   (khác ngôn ngữ, similarity thấp) → không false positive dự kiến; spot-check log.

9. **Docs:** `docs/skills/rss-sources.md` thêm section quốc tế (UA note, BOM Fed,
   summary-only rationale); README bảng nguồn.

## Todo list

- [ ] 5 YAML (cnbc, marketwatch, yahoofinance, fed, oilprice)
- [ ] Smoke test run_once 5 domains
- [ ] Verify sentiment neutral + language metadata trong DB
- [ ] Verify Fed BOM decode (phụ thuộc Phase 3)
- [ ] Đo cycle time, tune extract_full nếu cần
- [ ] Update docs (rss-sources.md, README.md)

## Success Criteria

- 5 domain active, item counts khớp verification ±50%.
- 100% EN articles: `metadata.language = "en"`, sentiment neutral/0.0.
- CNBC filter drop được non-finance items (spot-check fetched vs new).
- Cycle time 5 domains ≤2 phút steady-state.
- Quality: title+date+summary 100%; body-full chỉ yêu cầu cho fed/oilprice
  (extract_full: false domains được miễn body-full — ghi chú trong verify_quality
  interpretation, KHÔNG sửa script).

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| CNBC/Yahoo chặn UA/rotate chống bot | Trung bình | UA rotation sẵn có; nếu 403 liên tục → disable + note (pattern baodautu) |
| Summary-only EN làm giảm % quality gate tổng | Trung bình | Định nghĩa rõ: summary = body hợp lệ cho domain extract_full:false; theo dõi metric riêng |
| Feed URL CNBC (query param) đổi | Thấp | Heartbeat báo fetched=0 → cập nhật URL từ cnbc.com/rss-feeds |
| OilPrice opinionated noise | Thấp | Volume nhỏ (15); thêm filter sau nếu cần |

## Security Considerations

- Public feeds, không auth/secrets. Không gửi data ra ngoài.
- Fed là .gov — rate limit 3s lịch sự, không hammer.

## Next steps

Cycle-time guard toàn hệ (Phase 3 step 9) → nghiệm thu success metrics plan.md →
Phase 4 findings quyết định nguồn Layer 0/CTCK.
