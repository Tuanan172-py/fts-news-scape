# Domains — Ma trận nguồn tin

Cập nhật: **2026-09-07** · 24 domain, **8 enabled / 16 disabled**. Mỗi domain = 1 file
`config/domains/<name>.yaml`.

> ⚠️ **Đọc kỹ cột Enabled — bảng này từng sai suốt 2026-08→09** (ghi "22 enabled" trong khi thực
> tế chỉ có 3). Đã truth-sync bằng `grep -H "^enabled:" config/domains/*.yaml` ngày 2026-09-07.
>
> **19 domain tắt là CỐ Ý, không phải backlog** (owner xác nhận 2026-09-07). Hệ thống đã chuyển
> sang **Bronze-first**: mỗi bài phải có raw HTML byte-exact (`RawStore.save` trước mọi parse).
> `method: rss` generic **không lưu Bronze** — `RSSScraper.enrich()` không hề gọi `RawStore`.
> Vì vậy bật lại một nguồn **không phải** là đổi `enabled: true`; nó cần research riêng từng trang
> (selector detail, robots, format ngày, JS-rendering, anti-bot) + một scraper có capture.
> **Enabled ≡ có Bronze.** Đừng mass re-enable.
>
> Quy trình mở rộng nguồn: `plans/20260907-0834-market-sources-expansion/plan.md`.

## Bảng tổng hợp

| # | Domain | Loại | vi/en | Enabled | Method | Filter | Quirk chính |
|---|--------|------|-------|---------|--------|--------|-------------|
| 1 | cafef | API | vi | ✅ | REST + capture | – | `Type=1` bắt buộc; `/Date(ms+tz)/`; theo watchlist |
| 2 | **fireant** | API | vi | ✅ | **REST + capture JSON** | – | Bearer token; **Bronze là JSON** (web là SPA); field camelCase `postID`/`postSource`; permalink `/dashboard/content/{id}`. ⚠️ robots chặn ClaudeBot/GPTBot + `ai-train=no` — xem `domains/fireant/README.md` |
| 3 | tnck | API | vi | ✅ | **REST + capture** | – | **KHÔNG có RSS**; 9 zone; `date` epoch giây **NUMBER**; `phrase` bị ignore; `source_domain` NON-WWW ≠ tên config |
| 4 | vndirect | API | vi | ❌ | REST | – | no-auth; **aggregator** → fuzzy dedup |
| 5 | hose | Layer0 | vi | ❌ | RSS/JSON | – | React SPA → summary-only; api.hsx.vn |
| 6 | hnx | Layer0 | vi | ❌ | RSS | – | link port `:7978` → link_rewrites; BOM |
| 7 | vietstock | VN RSS | vi | ✅ | RSS + capture | – | Internal API unreachable → RSS primary |
| 8 | vnexpress | VN RSS | vi | ❌ | RSS | – | chung-khoan.rss 302 → chỉ kinh-doanh |
| 9 | vneconomy | VN RSS | vi | ✅ | RSS + capture | – | content:encoded rỗng; thay NDH |
| 10 | tuoitre | VN RSS | vi | ❌ | RSS | – | XML minified 1 dòng |
| 11 | thanhnien | VN RSS | vi | ❌ | RSS | – | thiếu `<?xml` declaration |
| 12 | znews | VN RSS | vi | ❌ | RSS | – | 50 items |
| 13 | cafebiz | VN RSS | vi | ❌ | RSS | – | home.rss superset (61 items) |
| 14 | vietnamplus | VN RSS | vi | ❌ | RSS | – | dùng www. (không en.) |
| 15 | vietnambiz | VN RSS | vi | ✅ | **RSS + capture** | – | khai utf-16 serve utf-8; **KHÔNG có `<article>`** → body `div.vnbcbc-body`; pubDate `GMT+7`; url `.htm` |
| 16 | dantri | VN RSS | vi | ❌ | RSS | – | BOM utf-8; không có chung-khoan.rss |
| 17 | vietnamnet | VN RSS | vi | ❌ | RSS | ✅ any | kinh-doanh 1000 items → filter bắt buộc |
| 18 | **baodautu** | **VN HTML** | vi | ✅ | **HTML listing + capture** | – | **RSS HỎNG VĨNH VIỄN ở server** (mọi feed = channel rỗng "Trang chủ"). `article` là item (KHÔNG phải `div.thumbblock`); body `#content_detail_news` (⚠️ `.content` là template JS); ngày text thuần `span.post-time`; `…/p<N>` thêm `/` là 404 |
| 19 | cnbc | Intl RSS | en | ❌ | RSS | ✅ any | Top News nhiễu → filter; browser UA |
| 20 | marketwatch | Intl RSS | en | ❌ | RSS | – | 10 items; detail paywall → summary-only |
| 21 | fed | Intl RSS | en | ❌ | RSS | – | BOM; signal macro cao; full text cap 10 |
| 22 | oilprice | Intl RSS | en | ❌ | RSS | – | 15 items; commentary; full text cap 10 |
| 23 | yahoofinance | Intl RSS | en | ❌ | RSS | ✅ none | block-list lifestyle; consent wall → summary-only |
| 24 | **thoibaotaichinhvietnam** | VN RSS | vi | ✅ | **RSS + capture** | – | **RSS chuyên mục là ẢO** (mọi `/{cat}/rss_feed/` trả cùng feed site-wide) → 1 feed; chuyên mục thật từ `meta article:section`; ngày ISO+07 sạch |

**Thống kê:** 24 domain — vi = 18 (gồm hose/hnx), en = 6.
**Enabled = 8**: cafef, vietstock, vneconomy, **vietnambiz**, **thoibaotaichinhvietnam**, **tnck**, **baodautu**, **fireant** (5 nguồn cuối mới/bật lại 2026-09-07). Cả 8 đều có Bronze capture.
**Disabled = 16**, toàn bộ do freeze Bronze-first 2026-08-03.
Filter: vietnamnet (any), cnbc (any), yahoofinance (none).

## Tài liệu chi tiết theo nhóm

- [api-scrapers.md](api-scrapers.md) — cafef, fireant, tnck, vndirect (REST API riêng)
- [exchange-layer0.md](exchange-layer0.md) — hose, hnx (sàn chính thống)
- [vn-rss.md](vn-rss.md) — báo VN qua RSS (gồm vietnambiz `rss_capture`)
- [html-scrapers.md](html-scrapers.md) — baodautu (HTML listing — không có RSS/API)

**Ngoài ma trận:** **NSO / Cục Thống kê** (báo cáo KTXH định kỳ) KHÔNG phải domain — nó là
driver riêng `src/pipeline/periodic_reports.py`, dedup theo `(report_type, period)`.
Xem [../design/16-periodic-report-scraper.md](../design/16-periodic-report-scraper.md).
- [intl-rss.md](intl-rss.md) — 5 báo tài chính quốc tế

## Watchlist (30 mã, `config/watchlist.yaml`)

`HPG VNM VIC VHM VCB BID CTG TCB MBB VPB ACB STB SHB HDB FPT SSI VND HCM VCI MWG MSN GAS PLX
POW GVR SAB VJC VRE BCM DGC`

Nhóm: **ngân hàng** (VCB BID CTG TCB MBB VPB ACB STB SHB HDB) · **chứng khoán** (SSI VND HCM VCI)
· **họ Vin** (VIC VHM VRE BCM) · **sản xuất/tiêu dùng** (HPG VNM MWG MSN SAB VJC DGC) · **năng
lượng** (GAS PLX POW GVR) · **công nghệ** (FPT). Dùng cho cafef/fireant (symbol-based) + tag ticker.

## Settings toàn cục (`config/settings.yaml`)

| Key | Giá trị |
|---|---|
| database.path | `data/monocle.db` |
| scheduler.interval_minutes | **15** |
| http.rate_limit | **3.0** giây/domain |
| http.timeout | 30 |
| http.max_retries | 3 |
| logging.level / dir | INFO / `logs` |
