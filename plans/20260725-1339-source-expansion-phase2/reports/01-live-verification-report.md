# Live Verification Report — Source Expansion Phase 2 (2026-07-25)

Batch curl toàn bộ ứng viên từ 2 research reports + ứng viên bổ sung. Đếm `<item>` thực tế.

## ✅ VERIFIED WORKING — VN (8 nguồn mới)

| Nguồn | Feed URL | Items | Pitfall |
|-------|----------|-------|---------|
| **VietnamBiz** | `https://vietnambiz.vn/chung-khoan.rss` | 30 | ⚠️ **encoding utf-16** — verify requests decode; thử thêm zone tai-chinh, vi-mo |
| **Dân trí** | `https://dantri.com.vn/rss/kinh-doanh.rss` | 100 | ⚠️ BOM (﻿) trước `<?xml` — cần strip BOM (lstrip không đủ); KHÔNG có chung-khoan.rss |
| **VietnamNet** | `https://vietnamnet.vn/rss/chung-khoan.rss` | **142** | volume lớn; kinh-doanh.rss có tới 1000 items → cần keyword filter hoặc giới hạn |
| **Tuổi Trẻ** | `https://tuoitre.vn/rss/kinh-doanh.rss` | 50 | XML minified 1 dòng |
| **Thanh Niên** | `https://thanhnien.vn/rss/kinh-te.rss` | 50 | thiếu `<?xml` declaration (bắt đầu thẳng `<rss`) — feedparser OK |
| **Znews** | `https://znews.vn/rss/kinh-doanh-tai-chinh.rss` | 50 | |
| **CafeBiz** | `https://cafebiz.vn/rss/cau-chuyen-kinh-doanh.rss` | 61 | researcher-01 nói không có RSS — SAI; nhiều zone khác cần khám phá |
| **VietnamPlus** | `https://www.vietnamplus.vn/rss/kinhte.rss` | 50 | bản tiếng Việt (không dùng en.) |

## ✅ VERIFIED WORKING — Quốc tế (5 nguồn, 6 feeds)

| Nguồn | Feed URL | Items | Ghi chú |
|-------|----------|-------|---------|
| **CNBC World Economy** | `https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258` | 30 | cần UA browser (HTTPClient đã có) |
| **CNBC Top News** | `...&id=100003114` | 30 | noise cao hơn → keyword filter |
| **MarketWatch Top** | `https://feeds.content.dowjones.io/public/rss/mw_topstories` | 10 | curated, noise thấp |
| **Yahoo Finance** | `https://finance.yahoo.com/news/rssindex` | 42 | |
| **Federal Reserve** | `https://www.federalreserve.gov/feeds/press_all.xml` | 20 | macro signal rất cao, tần suất thấp; BOM |
| **OilPrice** | `https://oilprice.com/rss/main` | 15 | commodity/dầu |

## ❌ DEAD / KHÔNG KHẢ THI (researcher đề xuất nhưng verify fail)

| Nguồn | Lý do |
|-------|-------|
| Stockbiz `en.stockbiz.vn/Rss.aspx` | empty response — **Tier-1 rec của researcher-02 chết** |
| HNX `hnx.vn/vi-vn/rss.html` | JS page, không phải feed — cần DevTools tìm feed thật (đưa vào sprint Layer 0) |
| Lao Động | anti-bot cookie JS |
| Saigon Times `/feed` | empty |
| Kitco | HTML, không RSS |
| Investing.com `rss/news_25.rss` | empty/blocked |
| nguoiquansat, vietnamfinance, markettimes | không có RSS endpoint chuẩn |
| dantri chung-khoan.rss | không tồn tại (dùng kinh-doanh) |

## Cần research sâu riêng (không RSS, giá trị cao)

- **Layer 0**: HOSE/HNX/SSC/CBTT disclosure — cần DevTools reverse (SPA/JS); HNX có thể có feed ẩn
- **CTCK research PDF**: SSI/VNDirect/BSC danh sách báo cáo public — HTML parse
- **24hmoney/Cophieu68** — reverse API nếu cần

## Hệ quả cho plan

1. 13 nguồn RSS mới add được ngay bằng YAML (generic RSSScraper) → tổng 19 domains.
2. **Cần tính năng mới: per-domain keyword filter** (include-list) cho feed noise cao (VietnamNet 1000 items, CNBC Top News) — giữ scope chứng khoán/kinh tế.
3. **Cần xử lý encoding**: utf-16 (VietnamBiz), BOM (Dân trí, Fed) trong RSSScraper.
4. Nguồn tiếng Anh: sentiment engine hiện VN-only → EN articles sẽ ra neutral; chấp nhận Phase 2, ghi metadata `language`.
5. Layer 0 + CTCK = sprint nghiên cứu riêng (DevTools), không chặn RSS sprint.
