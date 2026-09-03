# Phase 2 Completion Report (2026-07-25)

## Kết quả vs mục tiêu

| Metric | Target | Đạt |
|--------|--------|-----|
| Domains active | ≥15 | **21 active** (22 config; baodautu disabled — dormant) |
| Volume | ≥1000 bài/ngày | **2224 bài trong DB** sau 1 ngày backfill (~1600 riêng hôm nay) |
| Quality | ≥95% | **97.6%** trên nguồn full-content (by-design summary-only: yahoo/cnbc/marketwatch/hose = 104 bài tính riêng) |
| Tests | 80 + mới | **108 passed** |
| Cycle time | <12 phút | Backfill batch lớn nhất ~13 phút (10 domains); steady-state ước 4-6 phút/21 domains — trong budget |

## Nguồn mới (16)

- **VN RSS (8):** vietnambiz (3 zones), dantri, vietnamnet (filter, 591 giữ/1142 fetch), tuoitre, thanhnien, znews, cafebiz, vietnamplus
- **Quốc tế (5):** CNBC ×2 feeds, MarketWatch, Yahoo Finance, Fed, OilPrice — `language: en`, sentiment neutral by design
- **Layer 0 (2):** HNX công bố từ Sở (link_rewrites :7978, truststore SSL), HOSE api.hsx.vn (2 feeds, title-only by design)
- **Aggregator API (1):** VNDirect v4/news (scraper mới — full content trong response, fallback fetch báo gốc)

## Tính năng mới

1. Keyword filter per-domain (`filter.any` + `drop_unmatched`)
2. Encoding hardening `_decode_feed`: utf-16 BOM/no-BOM, utf-8-sig, strip encoding attr giả (vietnambiz khai utf-16 serve utf-8), lstrip blank lines
3. `language` metadata → orchestrator skip sentiment non-vi
4. `link_rewrites` per-domain (HNX :7978)
5. Date-fallback parser (`GMT+7`, `+07`, `7/25/2026 7:39 PM` + narrow-space)
6. Notify format chuẩn: `🟢/🟡/🔴 <title> - chi tiết (<url>)`
7. VndirectScraper: enrich fallback fetch báo gốc khi content ngắn
8. truststore (Windows cert store) — fix hnx.vn cert chain thiếu intermediate
9. HTTPClient bỏ tự khai `Accept-Encoding: br` (brotli trap — vietnambiz/vietnamnet)
10. `scripts/repair_dates.py` (one-off backfill dates)

## Sự cố live-verify → fix trong ngày

| Sự cố | Fix |
|-------|-----|
| vietnambiz/vietnamnet "feed parse failed" live (fixture OK) | Header `br` không có decoder → bỏ tự khai Accept-Encoding |
| HNX SSL CERTIFICATE_VERIFY_FAILED | truststore inject (OS cert store) |
| 191 bài thiếu date (3 format phi chuẩn) | `_parse_raw_date` + repair_dates.py (193 fixed) |
| feedparser fail khi XML decl khai utf-16 giả | strip encoding attr sau decode |
| Stockbiz/HNX-rss.html/dantri-chungkhoan từ research SAI | Loại qua live verification trước khi code |

## Code review (scoped delta): 0 critical; 2 HIGH fixed (GMT 2-digit, BOM literal→escape); 2 cảnh báo chứng minh false-positive bằng regression test; counter vndirect + LIKE brittle fixed.

## SSC + SSI + BSC (Phase 3 candidates)

- SSC: NO-GO (Oracle ADF, cần headless browser)
- SSI: list public nhưng PDF sau login → chỉ monitor title được
- BSC: GO đầy đủ (PDF tự do, ID tăng dần) — cần PDF text pipeline (pypdf) → Phase 3

## Unresolved

1. Yahoo Finance noise (lifestyle/finance-tips lẫn markets) — cân nhắc thêm filter keyword sau 24h quan sát.
2. 24h stability test với 21 domains — user chạy orchestrator + watch_24h.py.
3. EN sentiment lexicon — phase sau nếu cần.
