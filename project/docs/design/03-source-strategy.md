# Thiết kế — Chiến lược tiếp cận & xử lý các nguồn tin

Cập nhật: 2026-10-22 · Đối tượng: người thiết kế nguồn, muốn hiểu "tại sao chọn RSS/API,
xử lý các bẫy encoding/date/dedup ra sao".

## 1. Thứ tự ưu tiên phương thức (TDR-001)

**RSS > reverse API > HTML scraping.** Lý do: RSS coverage rộng, setup nhanh, ít vỡ khi
site đổi giao diện. API dùng cho nguồn không có RSS đủ sâu (cần theo mã CK) hoặc nguồn
môi giới. HTML tĩnh gần như không dùng (chỉ ở bước bóc chi tiết qua trafilatura).

### Cập nhật 2026-09-07 — tầng `rss_capture` (Bronze-first)

TDR-001 xếp hạng cách **lấy danh sách bài**. Nó không nói gì về **lưu trữ**, và từ khi có tầng
Bronze (design 06/07) thì "danh sách" là chưa đủ: mỗi bài phải có raw HTML byte-exact.

| Tier | `method` | Class | Bronze? |
|---|---|---|---|
| 1 | `rss` | `RSSScraper` | ❌ **không** — `enrich()` không gọi `RawStore` |
| **1b** | **`rss_capture`** | **`RssCaptureScraper`** (kế thừa `RSSScraper`) | ✅ **có** |
| 2 | `api` | `cafef`, `vndirect` | cafef ✅, vndirect ❌ |
| 2b | per-name | scraper riêng `tnck` (zone API), `fireant` (REST API), `vietstock`, `vneconomy` (RSS list) | ✅ |
| 3 | per-name HTML | scraper riêng `baodautu` (HTML listing) | ✅ (ngoại lệ TDR-001 có chủ ý) |

**Mọi nguồn mới dùng tier 1b trở lên.** Tier 1 chỉ còn tồn tại cho các domain lịch sử đang
disabled. Đây là lý do ~19 domain tắt từ 2026-08-03: mở rộng nguồn giờ là **Bronze-first**, cần
research riêng từng trang, không phải bật hàng loạt feed RSS.

Phân bổ hiện tại của 24 file `config/domains/*.yaml` theo `method`: **15 `rss`** (gồm hose/hnx), **2 `rss_capture`**
(vietnambiz, thoibaotaichinhvietnam), **2 `api`** (cafef, vndirect), **5 per-name** (baodautu, fireant, tnck, vietstock, vneconomy).
**Đang bật 8:** cafef, fireant, tnck, baodautu, vietstock, vneconomy, vietnambiz, thoibaotaichinhvietnam — tất cả có Bronze.

## 2. Bốn nhóm nguồn & cách tiếp cận

### Nhóm A — Báo VN qua RSS
Đang bật: vietnambiz, thoibaotaichinhvietnam (`rss_capture`), vietstock, vneconomy (scraper riêng, danh sách từ RSS).
Các báo tổng hợp còn lại (`method: rss`) đang tắt. Cùng 1 `RSSScraper`. Khác biệt chỉ là URL feed + vài quirk encoding. Chi tiết:
[../domains/vn-rss.md](../domains/vn-rss.md). Nguyên tắc: mỗi feed một zone kinh tế/chứng
khoán; nguồn nào feed quá rộng (vietnamnet kinh-doanh 1000 items) thì bật `filter.any`.

### Nhóm B — API môi giới/chuyên trang (cafef, tnck, vndirect, fireant)
Response JSON, cần code riêng vì schema khác nhau:
- **cafef / fireant** — theo **mã watchlist** (1 request/mã/cycle). fireant cần Bearer token.
- **tnck** — theo **zone × page** (không theo mã; tag ticker client-side). Từ 2026-09-07:
  9 zone + Bronze capture; **không có RSS** nên API là route duy nhất; `source_domain` non-www
  khác tên config `tnck` → dùng `resolve_source_domain()`.
- **vndirect** — 1 request lấy cả trang, nội dung nhúng sẵn; là **aggregator** (link báo gốc).

Chi tiết + quirk: [../domains/api-scrapers.md](../domains/api-scrapers.md).

### Nhóm C — Sàn chính thống HOSE/HNX (Layer 0)
Công bố thông tin niêm yết — độ tin cậy cao nhất. Trang chi tiết là React SPA nên
**summary-only** (title công bố = tín hiệu chính). hnx có bẫy link port nội bộ `:7978` →
xử bằng `link_rewrites`. Chi tiết: [../domains/exchange-layer0.md](../domains/exchange-layer0.md).

### Nhóm D — Báo tài chính quốc tế (cnbc, marketwatch, fed, oilprice, yahoofinance — en)
RSS tiếng Anh (`language: en`), hiện đều tắt. Nguồn nhiễu cao (cnbc Top News, yahoo lifestyle) dùng filter.
marketwatch/yahoo là summary-only vì detail paywall/consent-wall.

## 3. Ba bẫy lớn & cách hệ thống hoá giải

### 3.1 Encoding — `_decode_feed()` (`src/scrapers/rss_generic.py`)
Feed VN mắc đủ loại lỗi encoding. Một hàm xử tất cả, đọc bytes thô (`http.get_bytes`) thay
vì để requests đoán:

| Triệu chứng | Nguồn ví dụ | Xử lý |
|---|---|---|
| BOM utf-16 (`\xff\xfe`/`\xfe\xff`) | — | `decode("utf-16")` |
| utf-16 không BOM (null byte trong 400B đầu) | — | `decode("utf-16", errors="replace")` |
| BOM utf-8 | dantri, fed, hnx, hose | `decode("utf-8-sig")` |
| 4 dòng trống trước `<?xml` | baodautu | `lstrip("﻿ \t\r\n")` |
| Khai `encoding="utf-16"` nhưng serve utf-8 | vietnambiz | strip encoding attr khỏi 200B đầu (regex `_XML_DECL_ENC`) |
| Thiếu hẳn `<?xml` declaration | thanhnien | feedparser vẫn chấp nhận |
| Brotli bytes rác | vietnambiz/vietnamnet | HTTP client **không** tự khai `Accept-Encoding` (`HTTPClient._get_headers`, `src/crawler/http_client.py`) |

### 3.2 Ngày tháng — `_parse_raw_date()` (`src/scrapers/rss_generic.py`)
Ưu tiên `published_parsed` (struct_time UTC) → chuẩn hoá về `Asia/Ho_Chi_Minh`. Nếu chỉ có
string phi chuẩn: normalize `GMT+7`→`+0700`, `+07`→`+0700`; thử `parsedate_to_datetime`;
fallback strptime US-style `%m/%d/%Y %I:%M:%S %p` (tuoitre). Không tz → coi là giờ VN. Fail
hết → `""`. API scraper mỗi nguồn tự parse: cafef `/Date(ms+tz)/`, tnck epoch **giây**,
fireant/vndirect đã ISO sẵn.

### 3.3 Trùng lặp — chỉ bỏ bản sao kỹ thuật (rule 10, ADR-0013)
- Mọi URL vào sổ khám phá (`DedupCache.discover`, `src/db/dedup.py`) trước mọi bộ lọc.
- **Hash exact:** SHA-256(url+title) trong bảng `seen_articles`; chỉ bỏ qua khi sổ khám phá xác nhận bài đã `captured`.
  URL dạng khác của cùng bài → ghi `url_aliases`.
- Không có lớp fuzzy theo tiêu đề ở capture. Tin cùng nội dung đăng nhiều báo được gom ở Silver
  bằng cụm tin tất định (`src/pipeline/story_cluster.py`, ADR-0016), không xoá bài.

## 4. Lọc nội dung — `filter.any` / `filter.none` (`RSSScraper.parse_item`, `src/scrapers/rss_generic.py`)

Chỉ ba YAML còn khai `filter` (cnbc, vietnamnet, yahoofinance), cả ba đang tắt. Nguồn đang bật không lọc ở capture (ADR-0013).

Hai cơ chế bổ sung nhau, quét trên `title + " " + summary` (lowercase):
- **`filter.any`** (allow-list) + `drop_unmatched: true` → bài PHẢI chứa ≥1 keyword, else loại.
  Dùng cho feed rộng: vietnamnet (18 keyword tài chính), cnbc (18 keyword macro).
- **`filter.none`** (block-list) → chứa BẤT KỲ term nào thì loại. Luôn active. Dùng cho
  yahoofinance để chặn nhiễu lifestyle/retail-finance (mortgage, 401(k), credit card, …).
- Block check chạy **trước** allow check. Có thể kết hợp cả hai trong 1 domain.

Vì sao yahoo dùng block-list thay vì allow-list? Tiêu đề tin thị trường quá đa dạng (nhiều
tin chỉ là tên công ty: "Alphabet flops, Intel shocks") → allow-list sẽ loại nhầm. Block-list
chỉ cần liệt kê các chủ đề rác đã biết.

## 5. Nguồn đã thử và loại (2026-07-25)

Stockbiz (endpoint chết), Lao Động (anti-bot JS), Saigon Times (feed rỗng), Kitco/Investing.com
(không RSS/bị chặn), nguoiquansat/vietnamfinance/markettimes (không RSS), Reuters (RSS chết ~2020),
NDH (dormant → thay bằng vneconomy).

**baodautu — chẩn đoán lại 2026-09-07:** trước ghi "feed rỗng → disabled, có thể bật lại".
Sai. RSS hỏng **vĩnh viễn ở server** (mọi feed trả cùng channel rỗng `Trang chủ` + `<link>`
dị dạng `https://baodautu.vn//.rss`). Không phải dormant, không bao giờ tự khỏi.
→ Đã build **HTML listing scraper** (tier 3).

## 6. Câu hỏi mở

- hose (đang tắt) khai `method: rss` nhưng URL là JSON `api.hsx.vn/.../NewsByCateFeed/21` — cần xác nhận
  feedparser xử JSON-feed này ổn định hay cần code path riêng (đã verify chạy 2026-07-25 nhưng
  chưa có test cố định). Xem [../dev/05-known-issues.md](../dev/05-known-issues.md).
