# Domains — Báo VN qua RSS

Cập nhật: 2026-07-26 · 11 nguồn (10 enabled + baodautu disabled) + vietstock/vnexpress/vneconomy.
Tất cả dùng chung `RSSScraper`, `language: vi`, `extract_full: true` (trừ ghi chú), cap 30.
Verify 2026-07-24/25.

## Nguồn có cấu hình đặc thù

### vietstock — `vietstock.yaml`

- **4 feeds:** `/0/tin-moi.rss`, `/144/chung-khoan.rss`, `/733/doanh-nghiep.rss`, `/761/kinh-te/vi-mo.rss`.
- **Quirk:** Internal API (TopPageArticle…) unreachable/cần browser session → **RSS là PRIMARY**.
  pubDate `+0700`. Description chứa `<img>` → strip khi bóc summary. Index 60 feed tại `vietstock.vn/rss`.

### vnexpress — `vnexpress.yaml`

- **1 feed:** `/rss/kinh-doanh.rss`.
- **Quirk:** `chung-khoan.rss` **redirect 302** → chỉ dùng kinh-doanh. Body `fck_detail` → trafilatura OK.

### vneconomy — `vneconomy.yaml`

- **3 feeds:** `/chung-khoan.rss`, `/tai-chinh.rss`, `/thi-truong.rss`.
- **Quirk:** khai namespace `content:encoded` nhưng item **rỗng** → phải fetch detail. Thêm để
  **thay NDH** (dormant, quyết định 2026-07-24).

### vietnamnet — `vietnamnet.yaml` (**có filter**)

- **2 feeds:** `/rss/chung-khoan.rss` (142 items), `/rss/kinh-doanh.rss` (**1000 items!**).
- **filter.any** (18 keyword: chứng khoán, cổ phiếu, vn-index, trái phiếu, niêm yết, lãi suất,
  ngân hàng, tỷ giá, doanh nghiệp, vàng, hose, hnx, upcom, lợi nhuận, cổ tức, vĩ mô, gdp, lạm
  phát, fed), `drop_unmatched: true`.
- **Quirk:** kinh-doanh quá rộng → filter **bắt buộc**. Nếu vẫn nhiễu sau 24h: bỏ feed kinh-doanh.

### baodautu — `baodautu.yaml` (**DISABLED**)

- **3 feeds:** `/chung-khoan.rss`, `/dau-tu-tai-chinh.rss`, `/ngan-hang--bao-hiem.rss`.
- **Quirk:** `enabled: false` — feed XML hợp lệ nhưng **0 `<item>`** (dormant, verify nhiều
  UA/client). Có **4 dòng trống trước `<?xml`** (RSSScraper đã lstrip). Bật lại khi feed hồi.

## Nguồn "cắm là chạy" (quirk encoding nhẹ, RSSScraper tự xử)

| Domain      | Feed                                  | Quirk                                                                                              |
| ----------- | ------------------------------------- | -------------------------------------------------------------------------------------------------- |
| tuoitre     | `/rss/kinh-doanh.rss`               | XML minified 1 dòng; 50 items; date US-style`%m/%d/%Y %I:%M:%S %p`                              |
| thanhnien   | `/rss/kinh-te.rss`                  | thiếu`<?xml` declaration; 50 items                                                              |
| znews       | `/rss/kinh-doanh-tai-chinh.rss`     | 50 items                                                                                           |
| cafebiz     | `/rss/home.rss`                     | home.rss = superset (61 items); zone khác không tồn tại                                        |
| vietnamplus | `www.vietnamplus.vn/rss/kinhte.rss` | dùng bản**www.** (không en.); 50 items                                                    |
| vietnambiz  | `/chung-khoan.rss` +2               | khai`utf-16` nhưng serve **utf-8** → `_decode_feed` strip encoding attr; 30 items/zone |
| dantri      | `/rss/kinh-doanh.rss`               | **BOM utf-8** → utf-8-sig; KHÔNG có chung-khoan.rss; 100 items                            |

## Chung cho nhóm VN RSS

- Encoding: mọi bẫy (BOM/utf-16-mislabel/blank-line/thiếu decl) do `_decode_feed` xử tập trung.
- Ngày: `_parse_raw_date` chuẩn hoá về giờ VN.
- Symbols: `tag_tickers(title+summary, watchlist)` client-side.
- categories: tên feed (vd "Vietstock Chứng khoán").
- Muốn thêm báo VN mới: chỉ tạo YAML — xem [../dev/03-adding-a-source.md](../dev/03-adding-a-source.md).
