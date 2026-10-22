# Design 16 — PeriodicReportScraper (NSO / Cục Thống kê)

Cập nhật: 2026-09-07 · Trạng thái: **ĐÃ TRIỂN KHAI v1 + validate LIVE** (owner duyệt G2 2026-09-07).
Đọc kèm: [06-raw-html-capture](06-raw-html-capture.md) ·
[07-storage-layers](07-storage-layers-and-change-detection.md) ·
[03-source-strategy](03-source-strategy.md) ·
`plans/20260907-0834-market-sources-expansion/phase-05-nso-gated-deferred.md`

---

## 1. Gate G1 — ĐÃ QUA (2026-09-07)

Kết luận research ban đầu ("NSO bị chặn network, không xây được") **đã bị đảo ngược**.

| Probe | ~08:40 UTC | **15:21–15:25 UTC (G1 re-run)** |
|---|---|---|
| `https://www.nso.gov.vn/` | `curl (35)` reset | ✅ **200**, **12/12 probe**, 1.23–1.39 s |
| `https://www.nso.gov.vn/robots.txt` | reset | ✅ **200**, **12/12** |
| `http://www.nso.gov.vn/` (:80) | reset | ❌ **vẫn RST**, **12/12** |
| `https://www.gso.gov.vn/` | timeout | ❌ vẫn timeout — host **legacy**, IP khác (210.245.31.100) |

12 probe cách nhau 60 s, trải 15:21→15:35 UTC — **100% thành công, không một lần fail**.

**Kết luận:** chặn ban đầu là **chập chờn/tạm thời**, không vĩnh viễn. Chỉ **:443** đi được.
Dùng `nso.gov.vn`, bỏ `gso.gov.vn`.

⚠️ **Điều kiện tiên quyết trước khi triển khai:** chạy lại G1 **từ chính máy deploy**,
nhiều lần trong ngày. Cùng workstation này đã fail 6 giờ trước đó — chập chờn là rủi ro thật.

### robots.txt (2026-09-07)
```
User-agent: *
Disallow: /wp-admin/   /readme.html   /license.txt
Disallow: /wp-admin/admin-ajax.php    /wp-admin/images/*
```
Phần còn lại là blocklist agent hút site (Teleport, EmailCollector, WebZIP, BlackWidow…).
→ **Bài viết, `/wp-json/`, và `/wp-content/uploads/` đều ĐƯỢC PHÉP.** Không khai `Crawl-delay`.

---

## 2. Phát hiện quyết định: NSO là **WordPress + REST API công khai**

Đây là thay đổi lớn nhất so với giả định của phase-05 (vốn hình dung phải scrape HTML thủ công).

```
GET https://www.nso.gov.vn/wp-json/wp/v2/posts?tags=727&per_page=20&page=N
```

- **Tag 727** = `bao-cao-tinh-hinh-kinh-te-xa-hoi-hang-thang`
  ("Báo cáo tình hình kinh tế - xã hội") — **count: 337 bài**. Đây là tuyển tập chính thức,
  ổn định, không phải đoán từ slug.
- Trường trả về: `id, date, date_gmt, modified, modified_gmt, slug, link, title.rendered,
  content.rendered, excerpt, tags, categories, gso_document_type, acf, status, type`.
- Hỗ trợ `per_page`, `page`, `after=`/`before=` (lọc theo ngày) → **incremental sync tự nhiên**.

### Nhịp công bố (xác minh)
| Kỳ | `date` |
|---|---|
| Tháng 8 + 8 tháng 2026 | `2026-09-03T09:00:02` |
| Tháng 7 + 7 tháng 2026 | `2026-08-03T09:00:03` |
| Quý II + 6 tháng 2026 | `2026-07-03T08:56:25` |

→ **~ngày 3 hàng tháng, ~09:00 giờ VN.** Có biến thể **tháng / quý / năm** trong cùng một tag.

### ⚠️ Attachment KHÔNG có trong wp-json
`content.rendered` của API **không chứa** link `.docx/.xlsx` (chỉ có ảnh trang trí);
`acf: []`, `featured_media: 0`. Các file thật chỉ xuất hiện khi **render trang HTML**
(theme Avada/Fusion dựng bằng page-builder):

```
/wp-content/uploads/2026/09/01-Loi-van-T8.2026-final.docx   ← thuyết minh
/wp-content/uploads/2026/09/02-Bieu-T8.2026.xlsx            ← BẢNG SỐ LIỆU (giá trị cao nhất)
```

→ Bắt buộc **kiến trúc lai**: API để phát hiện + metadata, HTML để lấy attachment.

---

## 3. Vì sao KHÔNG dùng `BaseScraper`

| Đặc điểm NSO | Xung đột với `BaseScraper.run()` |
|---|---|
| ~1-3 bài/tháng | Vòng lặp 15 phút là lãng phí; cửa sổ công bố hẹp (ngày 3) |
| Cùng báo cáo mirror ở nhiều path (`/bai-top/`, `/tin-tuc-thong-ke/`, `/du-lieu-va-so-lieu-thong-ke/`, `/en/`) | dedup theo `url_title_hash` sẽ coi là **nhiều bài khác nhau** |
| Slug **không suy ra được** từ (loại, kỳ) | không thể xây URL; phải khám phá qua API |
| Payload chính là **file nhị phân** (.xlsx/.docx) | `RawStore` hiện chỉ lưu HTML text; `SilverBuilder` chạy trafilatura |
| Kỳ báo cáo (period) là khoá nghiệp vụ | `Article` không có khái niệm period |

### 🔴 Bằng chứng cứng cho "dedup theo period, không theo URL"
Mục tháng 6/2026 trên trang danh sách có slug:
```
/bai-top/2026/06/bao-cao-tinh-hinh-kinh-te-xa-hoi-thang-nam-va-5-thang-dau-nam-2025-2/
```
→ ghi **2025** (sai năm) **và** hậu tố **`-2`** (WordPress tự thêm khi trùng slug).
Không có hàm nào ánh xạ (report_type, period) → slug. **Khoá phải là `(report_type, period)`.**

---

## 4. Kiến trúc đề xuất

```
PeriodicReportSource (offline driver, KHÔNG phải BaseScraper)
  │
  1. DISCOVER   GET /wp-json/wp/v2/posts?tags=727&after=<watermark>&per_page=20
  │             → [{id, date, modified, slug, link, title}]
  │
  2. IDENTIFY   (report_type, period) ← parse từ title (nguồn ổn định nhất)
  │             "…tháng Tám và 8 tháng năm 2026"  → (monthly,   2026-08)
  │             "…Quý II và sáu tháng đầu năm 2026" → (quarterly, 2026-Q2)
  │             "…năm 2025"                         → (annual,    2025)
  │             ⚠️ KHÔNG parse từ slug (đã chứng minh sai năm + hậu tố -2)
  │
  3. DEDUP      khoá = (report_type, period)  — bảng periodic_reports (mới)
  │             đã có + `modified` không đổi  → skip
  │             đã có + `modified` đổi        → bản hiệu đính → capture bản mới, giữ bản cũ
  │
  4. CAPTURE    a. RawStore.save(post.link)            → Bronze HTML byte-exact (đã có sẵn)
  │             b. parse /wp-content/uploads/**.(xlsx|docx|pdf) từ HTML ĐÃ LƯU
  │             c. RawStore.save_binary(mỗi attachment) → Bronze nhị phân  [CẦN MỚI]
  │             robots gate + rate limit 3.0s + SourceBackoff dùng lại nguyên
  │
  5. SILVER     HTML → SilverBuilder (như cũ)
  │             XLSX → [CẦN MỚI] SheetExtractor: bảng → JSON/CSV chuẩn hoá
  │             DOCX → [CẦN MỚI] hoặc hoãn (thuyết minh trùng nội dung HTML)
  │
  6. SCHEDULE   cron: ngày 2-6 hàng tháng, 2 lần/ngày (08:00 & 14:00 VN)
                + 1 lần/tuần bắt kỳ quý/năm. KHÔNG nằm trong cycle 15 phút.
```

### Thành phần mới cần build

| Thành phần | Vì sao | Rủi ro |
|---|---|---|
| `RawStore.save_binary()` | Bronze hiện giả định body là text (`resp.text`, `_scan_images` dùng BS4). File nhị phân cần đường riêng: ghi bytes + `.meta.json` với `content_type`, `content_sha256`, **không** parse | thấp — cùng khuôn `_write_atomic` |
| bảng `periodic_reports` | khoá `(report_type, period)`, `wp_post_id`, `modified`, `html_path`, `attachments[]` | thấp — bảng mới, không đụng `articles` |
| `_parse_period(title)` | ánh xạ tiêu đề tiếng Việt → `(type, period)`. Số đếm tiếng Việt ("tháng Tám", "Quý II", "sáu tháng") | **trung bình** — cần test kỹ, đây là điểm dễ vỡ nhất |
| `SheetExtractor` (XLSX → JSON) | giá trị thật của NSO là bảng số liệu | **cao** — layout bảng thống kê phức tạp (merged cell, header nhiều tầng). **Đề xuất hoãn sang v2** |

### Không làm (YAGNI)
- ❌ `config/domains/nso.yaml` — NSO **không** là domain thứ 25.
- ❌ `src/scrapers/nso.py` đăng ký vào `REGISTRY`.
- ❌ headless browser / TLS-impersonation — API + HTML tĩnh là đủ.
- ❌ parse XLSX ở v1 — **lưu Bronze nhị phân trước**, trích số liệu sau (Bronze là WORM,
      trích lúc nào cũng được mà không cần fetch lại).

---

## 5. Phạm vi đề xuất cho v1 (nếu G2 được duyệt)

**Chỉ làm:** discover qua wp-json → identify (type, period) → dedup theo period →
Bronze HTML + Bronze nhị phân cho attachment → Silver HTML.
**Hoãn:** trích số liệu XLSX, tiếng Anh (`/en/`), các series khác (CPI/IIP/FDI/XNK/bán lẻ).

Ước lượng: ~1 bảng DB, ~1 module ~250 dòng, ~1 method mới trên `RawStore`, ~12 test.
Chi phí mạng: ~3 request/tháng ở steady state.

**Tiêu chí nghiệm thu**
- Bronze `.html` + `.xlsx`/`.docx` byte-exact, `sha256` khớp `.meta.json`.
- `(monthly, 2026-08)` chỉ tồn tại **một** bản ghi dù chạy lặp nhiều lần.
- Bản hiệu đính (`modified` đổi) tạo version mới, **không** ghi đè bản cũ.
- `robots` được tôn trọng; không request nào chạm `/wp-admin/`.
- Chạy lại toàn bộ từ Bronze không cần mạng.

---

## 6. Rủi ro

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Kết nối chập chờn (đã chứng kiến) | **cao** | G1 lại từ máy deploy; retry/backoff; job tần suất thấp nên fail 1 lần không mất dữ liệu |
| `_parse_period` sai trên tiêu đề lạ | **cao** | fail → **held + cảnh báo**, KHÔNG đoán bừa; test đủ 12 tháng + 4 quý + biến thể |
| Tag 727 bị đổi/xoá | trung bình | watch point; fallback: lọc `gso_document_type` |
| Layout bảng XLSX phức tạp | cao | **hoãn sang v2** — v1 chỉ lưu Bronze |
| wp-json bị tắt (plugin/WAF) | trung bình | fallback: trang danh sách HTML `/bao-cao-tinh-hinh-kinh-te-xa-hoi-hang-thang/` |
| Bản hiệu đính im lặng | trung bình | so `modified` mỗi lần poll |

---

## 7. Khuyến nghị

**Xây, nhưng chỉ khi cần SỐ LIỆU GỐC.** Nếu mục tiêu chỉ là *tin tức* về KTXH/đầu tư công thì
**TBTC + baodautu (đã chạy) là đủ** — cả hai đăng lại báo cáo trong vài giờ, đã chứng minh phủ
đúng beat (TBTC: *"Infographics 8 tháng giải ngân vốn đầu tư công đạt 509.557,5 tỷ đồng"*;
baodautu: *"Vốn FDI vào Việt Nam tăng mạnh, 8 tháng vượt 40 tỷ USD"*).

Giá trị riêng của NSO là **file XLSX số liệu gốc** — thứ không nguồn nào đăng lại.
Nếu phân tích cần con số gốc → xây. Nếu chỉ cần tin → không cần.

## 8. Câu hỏi cho owner (Gate G2)

1. Duyệt phạm vi v1 ở §5 (Bronze-first, **hoãn** trích XLSX)?
2. Có cần số liệu gốc XLSX không, hay proxy TBTC/baodautu là đủ?
3. Bảng `periodic_reports` riêng — hay nhét vào `articles` với cột period? (đề xuất: **bảng riêng**)
4. Ngoài KTXH hàng tháng, có cần CPI/IIP/FDI/XNK/bán lẻ ngay không? (đề xuất: **không**, v2)
5. Ai chạy G1 từ máy deploy, và khi nào?


---

## 9. TRIỂN KHAI v1 — HOÀN THÀNH 2026-09-07

### Thành phần đã build

| File | Vai trò |
|---|---|
| `src/pipeline/periodic_reports.py` | `PeriodicReportSource` + `parse_period()` + `extract_attachments()` |
| `scripts/fetch_periodic_reports.py` | CLI: `--after` `--limit` `--dry-run` `--no-attachments` `--list` |
| `src/crawler/raw_store.py` → `save_binary()` | Bronze nhị phân (.xlsx/.docx/.pdf) — ghi bytes, KHÔNG parse |
| `src/db/store.py` → bảng `periodic_reports` | khoá `UNIQUE(source, report_type, period, revision)` |
| `tests/test_periodic_reports.py` | 21 case |

**Đúng như thiết kế — KHÔNG có:** `config/domains/nso.yaml`, `src/scrapers/nso.py`,
đăng ký `REGISTRY`, headless browser. NSO **không** là domain thứ 25.

### Validate LIVE (2026-09-07)

```
$ python scripts/fetch_periodic_reports.py --dry-run --per-page 12
discovered=12    → 12/12 parse đúng kỳ, 0 held
  ('monthly',  '2026-08')  2026-09-03   ('quarterly','2026-Q2')  2026-07-03
  ('monthly',  '2026-07')  2026-08-03   ('quarterly','2026-Q1')  2026-04-04
  ('monthly',  '2026-05')  2026-06-03   ('quarterly','2025-Q4')  2026-01-05
  ...

$ python scripts/fetch_periodic_reports.py --limit 3
periodic-reports: discovered=5 captured=3 revised=0 skipped_unchanged=0
                  held_unparsed=0 failed=0 attachments=6

$ python scripts/fetch_periodic_reports.py --limit 3      # chạy lại
periodic-reports: ... captured=0 ... skipped_unchanged=3 ...   ← IDEMPOTENT
```

Bronze sinh ra:
```
data/raw_html/nso.gov.vn/20260907/
  monthly-2026-08-r1.html                            116 KB
  monthly-2026-08-r1__01-Loi-van-T8.2026-final.docx  1.4 MB
  monthly-2026-08-r1__02-Bieu-T8.2026.xlsx           867 KB   ← BẢNG SỐ LIỆU
  monthly-2026-07-r1.*  quarterly-2026-Q2-r1.*       (+ .meta.json mỗi file)
```

**XLSX kiểm chứng mở được thật:** `zipfile.is_zipfile()` → True, có
`xl/worksheets/sheet4..7.xml`, `sha256` khớp `.meta.json`, `capture_status: ok`.

### Bất biến được test khoá

- dedup theo `(report_type, period)` — test dùng slug **sai năm + hậu tố `-2`** và id khác
  → vẫn `skipped_unchanged`, **không fetch lại trang**.
- `modified` đổi → **revision mới**, bản cũ còn nguyên (`r1` + `r2` cùng tồn tại).
- không parse được kỳ → **held + error**, không capture, không ghi DB, **không đoán bừa**.
- attachment byte-exact + sha256 khớp.
- discover lỗi (HTTP 503) → summary rỗng + error, **không raise**.

### Hai bug tự tìm ra khi validate

1. **Đuôi file lặp** `.xlsx.xlsx` — `_safe_key` giữ cả đuôi trong khi `save_binary` tự gắn
   đuôi theo Content-Type. → `_safe_key` bỏ đuôi. Có test.
2. **Mất case tên file** — `extract_attachments` hạ chữ cả path để so đuôi, nên
   `02-Bieu-T8.2026.xlsx` thành `02-bieu-t8.2026.xlsx`. → chỉ hạ chữ khi **so khớp**,
   `filename` giữ nguyên case gốc. Có test.

### Lịch chạy đề xuất (chưa gắn cron)

```
# ngày 2-6 hàng tháng, 08:00 & 14:00 giờ VN (NSO công bố ~ngày 3, ~09:00)
0 8,14 2-6 * *  python scripts/fetch_periodic_reports.py --after <YYYY-MM-01>
# 1 lần/tuần bắt báo cáo quý/năm
0 9 * * 1       python scripts/fetch_periodic_reports.py --per-page 10
```
Exit code **1** khi có `held_unparsed` hoặc `failed` → cron báo động được.

### Còn hoãn sang v2 (đúng chủ ý)

- **Trích số liệu XLSX** → JSON/CSV. Bronze là WORM nên trích lúc nào cũng được, không cần
  fetch lại. Layout bảng thống kê (merged cell, header nhiều tầng) là việc riêng.
- Bản tiếng Anh `/en/`, các series CPI/IIP/FDI/XNK/bán lẻ.
- Silver cho báo cáo định kỳ (hiện chỉ có Bronze + hàng DB).

### Việc còn lại cho owner

- [ ] Chạy `--dry-run` **từ máy deploy** vài lần trong ngày (chập chờn đã gặp lúc ~08:40).
- [ ] Quyết có gắn cron hay chạy tay hàng tháng.
- [ ] Quyết có cần v2 (trích XLSX) hay Bronze là đủ.
