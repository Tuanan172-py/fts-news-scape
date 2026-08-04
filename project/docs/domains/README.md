# Domains — Ma trận nguồn tin

Cập nhật: 2026-07-26 · 23 domain (22 enabled + 1 disabled). Verify live: Phase 1 = 2026-07-24,
Phase 2 = 2026-07-25. Mỗi domain = 1 file `config/domains/<name>.yaml`.

## Bảng tổng hợp

| # | Domain | Loại | vi/en | Enabled | Method | Filter | Quirk chính |
|---|--------|------|-------|---------|--------|--------|-------------|
| 1 | cafef | API | vi | ✅ | REST | – | `Type=1` bắt buộc; `/Date(ms+tz)/`; theo watchlist |
| 2 | fireant | API | vi | ✅ | REST | – | Bearer token; hết hạn → self-disable |
| 3 | tnck | API | vi | ✅ | REST | – | gzip; `phrase` bị server ignore; date epoch giây |
| 4 | vndirect | API | vi | ✅ | REST | – | no-auth; **aggregator** → fuzzy dedup |
| 5 | hose | Layer0 | vi | ✅ | RSS/JSON | – | React SPA → summary-only; api.hsx.vn |
| 6 | hnx | Layer0 | vi | ✅ | RSS | – | link port `:7978` → link_rewrites; BOM |
| 7 | vietstock | VN RSS | vi | ✅ | RSS | – | Internal API unreachable → RSS primary |
| 8 | vnexpress | VN RSS | vi | ✅ | RSS | – | chung-khoan.rss 302 → chỉ kinh-doanh |
| 9 | vneconomy | VN RSS | vi | ✅ | RSS | – | content:encoded rỗng; thay NDH |
| 10 | tuoitre | VN RSS | vi | ✅ | RSS | – | XML minified 1 dòng |
| 11 | thanhnien | VN RSS | vi | ✅ | RSS | – | thiếu `<?xml` declaration |
| 12 | znews | VN RSS | vi | ✅ | RSS | – | 50 items |
| 13 | cafebiz | VN RSS | vi | ✅ | RSS | – | home.rss superset (61 items) |
| 14 | vietnamplus | VN RSS | vi | ✅ | RSS | – | dùng www. (không en.) |
| 15 | vietnambiz | VN RSS | vi | ✅ | RSS | – | khai utf-16 nhưng serve utf-8 |
| 16 | dantri | VN RSS | vi | ✅ | RSS | – | BOM utf-8; không có chung-khoan.rss |
| 17 | vietnamnet | VN RSS | vi | ✅ | RSS | ✅ any | kinh-doanh 1000 items → filter bắt buộc |
| 18 | baodautu | VN RSS | vi | ❌ | RSS | – | **DISABLED** — feed 0 item (dormant) |
| 19 | cnbc | Intl RSS | en | ✅ | RSS | ✅ any | Top News nhiễu → filter; browser UA |
| 20 | marketwatch | Intl RSS | en | ✅ | RSS | – | 10 items; detail paywall → summary-only |
| 21 | fed | Intl RSS | en | ✅ | RSS | – | BOM; signal macro cao; full text cap 10 |
| 22 | oilprice | Intl RSS | en | ✅ | RSS | – | 15 items; commentary; full text cap 10 |
| 23 | yahoofinance | Intl RSS | en | ✅ | RSS | ✅ none | block-list lifestyle; consent wall → summary-only |

**Thống kê:** vi = 17 (gồm hose/hnx), en = 6. Filter: vietnamnet (any), cnbc (any), yahoofinance (none).

## Tài liệu chi tiết theo nhóm

- [api-scrapers.md](api-scrapers.md) — cafef, fireant, tnck, vndirect (REST API riêng)
- [exchange-layer0.md](exchange-layer0.md) — hose, hnx (sàn chính thống)
- [vn-rss.md](vn-rss.md) — 11 báo VN qua RSS
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
