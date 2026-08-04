# Domain Skill: RSS Sources

Generic `RSSScraper` (`src/scrapers/rss_generic.py`) — domain RSS mới = 1 YAML, zero code.
Feeds verified live: 2026-07-24 (Phase 1) + 2026-07-25 (Phase 2).

## Schema mở rộng (Phase 2)

```yaml
language: vi              # default "vi"; "en" → orchestrator skip sentiment VN (neutral/0.0)
filter:                   # optional — keyword include-filter cho feed noise cao
  any: ["chứng khoán", "cổ phiếu"]   # case-insensitive substring trên title+summary
  drop_unmatched: true    # default true khi có filter
```

## Encoding pitfalls (xử lý tự động bởi `_decode_feed`)

| Case | Nguồn | Xử lý |
|------|-------|-------|
| Khai `encoding="utf-16"` nhưng serve utf-8 | VietnamBiz | decode bytes + strip encoding attr khỏi XML declaration |
| BOM utf-8 trước `<?xml` | Dân trí, Fed | `utf-8-sig` |
| utf-16 thật (BOM FF FE) | (phòng hờ) | decode utf-16 |
| Blank lines trước `<?xml` | Báo Đầu tư | lstrip |
| Thiếu `<?xml` declaration | Thanh Niên | feedparser chấp nhận |

## Feed inventory

| Domain | Feed | Ghi chú |
|--------|------|---------|
| **vietstock.vn** | `/0/tin-moi.rss`, `/144/chung-khoan.rss`, `/733/doanh-nghiep.rss`, `/761/kinh-te/vi-mo.rss` | Index `https://vietstock.vn/rss` — 60 feeds. pubDate `+0700`. RSS là PRIMARY method (internal API cần browser session) |
| **vnexpress.net** | `/rss/kinh-doanh.rss` | `chung-khoan.rss` → 302 (không dùng) |
| **baodautu.vn** | `/chung-khoan.rss`, `/dau-tu-tai-chinh.rss`, `/ngan-hang--bao-hiem.rss` | Index `rssMain.html`. ⚠️ **DISABLED 2026-07-24**: feeds trả XML hợp lệ nhưng 0 items (dormant). Feed cũng có 4 dòng trống trước `<?xml` (đã xử lý lstrip) |
| **vneconomy.vn** | `/chung-khoan.rss`, `/tai-chinh.rss`, `/thi-truong.rss` | Namespace content:encoded khai báo nhưng item không chứa — detail-fetch thường. Thay NDH (dormant) |
| **vietnambiz.vn** | `/chung-khoan.rss`, `/tai-chinh.rss`, `/vi-mo.rss` | 30 items/zone. Encoding trap (xem bảng trên) |
| **dantri.com.vn** | `/rss/kinh-doanh.rss` | 100 items, BOM. Không có chung-khoan.rss |
| **vietnamnet.vn** | `/rss/chung-khoan.rss` (142), `/rss/kinh-doanh.rss` (1000!) | kinh-doanh BẮT BUỘC filter keyword |
| **tuoitre.vn** | `/rss/kinh-doanh.rss` | 50 items, XML minified 1 dòng |
| **thanhnien.vn** | `/rss/kinh-te.rss` | 50 items, thiếu XML declaration |
| **znews.vn** | `/rss/kinh-doanh-tai-chinh.rss` | 50 items |
| **cafebiz.vn** | `/rss/home.rss` | 61 items (superset các zone) |
| **vietnamplus.vn** | `/rss/kinhte.rss` | 50 items, dùng bản www. (không en.) |

## Nguồn quốc tế (language: en — sentiment skip, classifier chỉ gán feed name)

| Nguồn | Feed | Ghi chú |
|-------|------|---------|
| **CNBC** | `search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258` (World Economy), `&id=100003114` (Top News) | filter keyword bắt buộc cho Top News; summary-only |
| **MarketWatch** | `feeds.content.dowjones.io/public/rss/mw_topstories` | 10 items curated; detail paywall → summary-only |
| **Yahoo Finance** | `finance.yahoo.com/news/rssindex` | 42 items; consent wall → summary-only |
| **Federal Reserve** | `federalreserve.gov/feeds/press_all.xml` | BOM; signal macro rất cao; full text (cap 10) |
| **OilPrice** | `oilprice.com/rss/main` | 15 items dầu/năng lượng; full text (cap 10) |

## Nguồn đã thử và loại (2026-07-25)

Stockbiz (endpoint chết), Lao Động (anti-bot JS), Saigon Times/feed (empty), Kitco (không RSS), Investing.com (blocked), nguoiquansat/vietnamfinance/markettimes (không RSS), HNX rss.html (JS page — xem probe Layer 0), Reuters (RSS chết từ ~2020).

## Behavior

- `pubDate` mọi format → feedparser normalize UTC → convert `Asia/Ho_Chi_Minh`.
- Summary chứa HTML (img tag Vietstock) → strip qua `extract_text`.
- Ticker tagging client-side (`core/tickers.py`) trên title + summary.
- Feed chết → WARN + tiếp feed khác trong domain (isolation).
- Detail fetch: trafilatura full page, raw HTML bảo toàn; cap 30/cycle/domain.
- `categories` = tên feed (vd "Vietstock Chứng khoán").

## Thêm nguồn RSS mới

```yaml
# config/domains/<name>.yaml
name: <name>
method: rss
rss:
  feeds:
    - {url: "https://...", name: "Tên hiển thị"}
detail: {extract_full: true, max_details_per_cycle: 30}
```

Không cần code — `RSSScraper` generic nhận mọi domain `method: rss`.
