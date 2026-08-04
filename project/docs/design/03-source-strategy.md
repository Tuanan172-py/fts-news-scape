# Thiết kế — Chiến lược tiếp cận & xử lý các nguồn tin

Cập nhật: 2026-07-26 · Đối tượng: người thiết kế nguồn, muốn hiểu "tại sao chọn RSS/API,
xử lý các bẫy encoding/date/dedup ra sao".

## 1. Thứ tự ưu tiên phương thức (TDR-001)

**RSS > reverse API > HTML scraping.** Lý do: RSS coverage rộng, setup nhanh, ít vỡ khi
site đổi giao diện. API dùng cho nguồn không có RSS đủ sâu (cần theo mã CK) hoặc nguồn
môi giới. HTML tĩnh gần như không dùng (chỉ ở bước bóc chi tiết qua trafilatura).

Kết quả phân bổ 23 domain: **18 RSS** (gồm cả hose/hnx) + **4 API custom** (cafef, tnck,
vndirect, fireant) + **1 disabled** (baodautu).

## 2. Bốn nhóm nguồn & cách tiếp cận

### Nhóm A — Báo VN qua RSS (17 nguồn vi)
Cùng 1 `RSSScraper`. Khác biệt chỉ là URL feed + vài quirk encoding. Chi tiết:
[../domains/vn-rss.md](../domains/vn-rss.md). Nguyên tắc: mỗi feed một zone kinh tế/chứng
khoán; nguồn nào feed quá rộng (vietnamnet kinh-doanh 1000 items) thì bật `filter.any`.

### Nhóm B — API môi giới/chuyên trang (cafef, tnck, vndirect, fireant)
Response JSON, cần code riêng vì schema khác nhau:
- **cafef / fireant** — theo **mã watchlist** (1 request/mã/cycle). fireant cần Bearer token.
- **tnck** — theo **zone × page** (không theo mã; tag ticker client-side).
- **vndirect** — 1 request lấy cả trang, nội dung nhúng sẵn; là **aggregator** (link báo gốc).

Chi tiết + quirk: [../domains/api-scrapers.md](../domains/api-scrapers.md).

### Nhóm C — Sàn chính thống HOSE/HNX (Layer 0)
Công bố thông tin niêm yết — độ tin cậy cao nhất. Trang chi tiết là React SPA nên
**summary-only** (title công bố = tín hiệu chính). hnx có bẫy link port nội bộ `:7978` →
xử bằng `link_rewrites`. Chi tiết: [../domains/exchange-layer0.md](../domains/exchange-layer0.md).

### Nhóm D — Báo tài chính quốc tế (cnbc, marketwatch, fed, oilprice, yahoofinance — en)
RSS tiếng Anh. Được đánh dấu `language: en` → orchestrator **ép sentiment neutral** (lexicon
VN không áp cho tiếng Anh). Nguồn nhiễu cao (cnbc Top News, yahoo lifestyle) dùng filter.
marketwatch/yahoo là summary-only vì detail paywall/consent-wall.

## 3. Ba bẫy lớn & cách hệ thống hoá giải

### 3.1 Encoding — `_decode_feed()` (`rss_generic.py:31-46`)
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
| Brotli bytes rác | vietnambiz/vietnamnet | HTTP client **không** tự khai `Accept-Encoding` (`http_client.py:80-82`) |

### 3.2 Ngày tháng — `_parse_raw_date()` (`rss_generic.py:49-76`)
Ưu tiên `published_parsed` (struct_time UTC) → chuẩn hoá về `Asia/Ho_Chi_Minh`. Nếu chỉ có
string phi chuẩn: normalize `GMT+7`→`+0700`, `+07`→`+0700`; thử `parsedate_to_datetime`;
fallback strptime US-style `%m/%d/%Y %I:%M:%S %p` (tuoitre). Không tz → coi là giờ VN. Fail
hết → `""`. API scraper mỗi nguồn tự parse: cafef `/Date(ms+tz)/`, tnck epoch **giây**,
fireant/vndirect đã ISO sẵn.

### 3.3 Trùng lặp — dedup 2 lớp (TDR-003)
- **Lớp 1 (hash exact):** SHA-256(url+title) trong bảng `seen_articles`. Bắt trùng cùng URL.
- **Lớp 2 (fuzzy cross-domain):** `rapidfuzz.token_set_ratio ≥ 90`, cửa sổ 48h, **chỉ so
  giữa domain khác nhau** (cùng domain đã do lớp 1 lo). Chịu được đảo mệnh đề tiêu đề.
  Quan trọng cho **vndirect (aggregator)** và tin cùng nội dung đăng nhiều báo.

## 4. Lọc nội dung — `filter.any` / `filter.none` (`rss_generic.py:160-170`)

Hai cơ chế bổ sung nhau, quét trên `title + " " + summary` (lowercase):
- **`filter.any`** (allow-list) + `drop_unmatched: true` → bài PHẢI chứa ≥1 keyword, else loại.
  Dùng cho feed rộng: vietnamnet (18 keyword tài chính), cnbc (18 keyword macro).
- **`filter.none`** (block-list) → chứa BẤT KỲ term nào thì loại. Luôn active. Dùng cho
  yahoofinance để chặn nhiễu lifestyle/retail-finance (mortgage, 401(k), credit card, …).
- Block check chạy **trước** allow check. Có thể kết hợp cả hai trong 1 domain.

Vì sao yahoo dùng block-list thay vì allow-list? Tiêu đề tin thị trường quá đa dạng (nhiều
tin chỉ là tên công ty: "Alphabet flops, Intel shocks") → allow-list sẽ loại nhầm. Block-list
chỉ cần liệt kê các chủ đề rác đã biết.

## 5. language: vi/en — vì sao ép EN neutral

Lexicon sentiment là tiếng Việt (segmented). Chạy nó trên tiếng Anh chỉ ra 0.0 (không match)
— nhưng thay vì để "tình cờ đúng", orchestrator **chủ động** set `("neutral", 0.0)` cho mọi
bài `language != "vi"` (`orchestrator.py:107-109`). Rõ ràng, không tốn công segment, không
gây hiểu nhầm rằng engine "đã phân tích" bài tiếng Anh.

## 6. Nguồn đã thử và loại (2026-07-25)

Stockbiz (endpoint chết), Lao Động (anti-bot JS), Saigon Times (feed rỗng), Kitco/Investing.com
(không RSS/bị chặn), nguoiquansat/vietnamfinance/markettimes (không RSS), Reuters (RSS chết ~2020),
NDH (dormant → thay bằng vneconomy), baodautu (feed rỗng → disabled, có thể bật lại).

## 7. Câu hỏi mở

- hose khai `method: rss` nhưng URL là JSON `api.hsx.vn/.../NewsByCateFeed/21` — cần xác nhận
  feedparser xử JSON-feed này ổn định hay cần code path riêng (đã verify chạy 2026-07-25 nhưng
  chưa có test cố định). Xem [../dev/05-known-issues.md](../dev/05-known-issues.md).
