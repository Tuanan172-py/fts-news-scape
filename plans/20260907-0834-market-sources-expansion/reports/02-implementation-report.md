# Report 02 — Implementation complete, 2026-09-07

Cả 5 phase đã chạy. `pytest -q` = **304 passed, 0 failed** (trước khi bắt đầu: 273).
Nguồn enabled: **3 → 7**. Bronze dir = Silver dir = domain enabled = **7/7/7** (nhất quán).

---

## 1. Kết quả live (evidence)

| Nguồn | Cycle | Bronze `ok` | sha256 | `missing[]` | Silver | quality |
|---|---|---|---|---|---|---|
| **vietnambiz** | 180 fetched / **174 new** / 0 err | 30/30 | 30/30 | none | 30/30 | high |
| **thoibaotaichinhvietnam** | 25 fetched / **24 new** / 0 err | 24/24 | 24/24 | none | 24/24 | high |
| **tnck** | 360 fetched / **356 new** / 0 err | 40/40 | 40/40 | none | 40/40 | high |
| **baodautu** | 173 fetched / **132 new** / 0 err | 30/30 | 30/30 | none | 30/30 | high |

- Silver derive tổng: `processed=164 ok=164 held=0` + `40/40/0` + `30/30/0` → **0 held** xuyên suốt.
- Backfill vietnambiz: `selected=170 refetched=140 skipped=30` — 30 skip chứng minh **Bronze WORM**
  (không ghi đè bản đã capture).
- Header whitelist: `.meta.json` chỉ có `content-type[, content-length], server, date` —
  **không rò `Set-Cookie`**.
- `report_drift.py`: **0** SELECTOR_BROKEN/TEMPLATE_DRIFT cho 4 nguồn mới.
  (2 mục tồn đọng là **cafef.vn từ 2026-09-04** — có trước, không thuộc phạm vi này.)

## 2. Phát hiện lớn ngoài kế hoạch

### 2.1 TBTC — RSS theo chuyên mục là **ẢO** (phase-02)
Kế hoạch định dùng **9 feed chuyên mục** `/{category}/rss_feed/`. Chúng trả 200 + 25 item nên
trông đúng. Verify sâu: **server bỏ qua path chuyên mục** — `chung-khoan`, `thue-hai-quan`,
`bat-dong-san` và root đều trả **cùng 25 item**, cùng `pubDate`, channel `<link>` = `/trang-chu`.
→ 9 feed = fetch trùng 9 lần + **gắn nhãn chuyên mục SAI**.
**Sửa:** 1 feed duy nhất; chuyên mục thật lấy từ `<meta property="article:section">`.
**Chi phí:** thêm tuỳ chọn generic `detail.category_meta` (~20 dòng) vào class phase-01 —
**sai lệch có chủ ý** so với tiêu chí "zero new Python" (S2) của phase-02.

### 2.2 baodautu — `div.thumbblock` khớp **0 node** (phase-04)
Kế hoạch ghi item selector `div.thumbblock`. Sai: class `thumbblock` nằm trên thẻ **`<a>` ảnh**,
không phải `<div>` (dù chuỗi xuất hiện 35 lần trong HTML). Item thật là **`<article>`**.
Tệ hơn: trong mỗi `<article>`, link ảnh (**không có text**) đứng **trước** link tiêu đề →
`select_one()` vớ phải link ảnh rồi bỏ qua ⇒ **mất sạch bài**.
**Sửa:** duyệt hết anchor, lấy cái đầu tiên vừa có text vừa khớp `link_pattern`.

### 2.3 NSO — G1 **PASS**, đảo ngược kết luận research (phase-05)
Sáng nay `nso.gov.vn` reset TCP từ 2 đường mạng. 15:03 UTC: **`https://` trả 200**, ổn định
3/3 request (1.2–1.4s). Chỉ `:80` còn reset; `gso.gov.vn` là host legacy đã chết.
→ Chặn trước đó là **chập chờn**, không vĩnh viễn.
robots cho phép bài viết (`User-agent: *` chỉ chặn `/wp-admin/`…).
**Bằng chứng củng cố thiết kế:** báo cáo tháng 6/2026 có slug
`…-thang-nam-va-5-thang-dau-nam-2025-2/` — **sai năm + hậu tố `-2`**. Slug không suy ra được
từ (loại, kỳ) ⇒ dedup **bắt buộc** theo `(report_type, period)`, không theo URL.
**Đã DỪNG đúng thiết kế:** không viết scraper, không tạo `nso.yaml`. Chờ owner quyết **G2**.

## 3. Sửa nợ kỹ thuật kèm theo

- **Bẫy `.vn`-suffix** (`domain_check.py:152`, `domain_reporter.py:126,170`) → thay bằng
  `src.core.config.resolve_source_domain()`. Chứng minh: report TNCK giờ ghi
  `## tinnhanhchungkhoan.vn` với **354 bài** (trước sẽ là `tnck.vn` → 0 bài).
- **Docs truth-sync:** `docs/domains/README.md` ghi "22 enabled" trong khi thực tế là 3.
  Đã sửa + ghi rõ 17 domain tắt là **cố ý** (Bronze-first), không phải backlog.
- **`docs/dev/03-adding-a-source.md`**: thêm §2b (`rss_capture`), cảnh báo `content_selector`
  là **bắt buộc**, checklist PR mở rộng (Bronze/Silver/schema.yaml/docs/verify).
- **`docs/domains/html-scrapers.md`**: file mới, chuẩn cho nhóm HTML-listing.
- **`docs/skills/tnck.md`**: sửa sai `date` "string" → **NUMBER**; ghi rõ không có RSS.
- **Fixtures thật** cho cả 4 nguồn (không mock giả).

## 4. Việc còn mở (cần owner)

| # | Việc | Mức |
|---|---|---|
| 1 | ~~Gate G2 NSO~~ → **ĐÃ MỞ** (owner duyệt). G1 re-run 12/12 PASS. Design doc xong. Còn: chạy G1 từ **máy deploy** + chốt 5 câu hỏi §8. | đang chờ |
| 2 | ~~Backlog lần đầu~~ → **ĐÃ ĐÓNG** bằng `scripts/maintenance/backfill_deferred.py` (Bronze-first). vietnambiz 48.8% → **100.0% PASS**. `enrich_deferred.py` đã xoá. | xong |
| 3 | **TNCK zone 8/13/36/43** — review sau 7 ngày đo `metadata.zone_id`. | theo lịch |
| 4 | **TBTC watch `tbtc-w3`** — nếu upstream sửa feed chuyên mục thì bỏ `category_meta`, quay lại nhiều feed. | định kỳ |
| 5 | **baodautu 04b (sitemap backstop)** — **chưa cần**: date-parse hiện **100%**. Chỉ mở nếu < 98%. | gated |
| 6 | **`vneconomy` thiếu `domains/vneconomy/`** — 6/7 nguồn enabled có contract, vneconomy chưa. | nợ nhỏ |
| 7 | **cafef.vn**: 2 SELECTOR_BROKEN từ 2026-09-04 + lỗi DNS `getaddrinfo failed` trong log. Có trước, chưa xử lý. | có sẵn |
| 8 | **`.venv` đã sửa**: `pyvenv.cfg` trỏ máy khác (`C:\\Users\\anpt\\...anaconda3`). Đã trỏ lại `pythoncore-3.14-64`. Backup `.venv/pyvenv.cfg.bak`. | đã xong |

## 5. Câu hỏi chưa giải

- TBTC: bộ chuyên mục nên mở rộng? (hiện feed site-wide gộp cả xã hội/đời sống — chưa bật filter)
- baodautu: listing có thật sự newest-first không? (giả định, chưa verify — chỉ ảnh hưởng độ tươi)
- TNCK: quảng cáo `div[id^=adsWeb_]` lọt vào Silver `cleaned_text` — có cần strip domain-aware
  trong `extractor.py` không? (sẽ là rule domain-specific đầu tiên trong module cố tình generic)
- Trùng lặp beat đầu tư công giữa TBTC / baodautu / vneconomy: corroboration hay nhiễu?


---

# Bổ sung — sau quyết định owner (2026-09-07, phiên 2)

Owner duyệt 3 việc: (1) mở G2 NSO + chạy lại G1, (2) chấp nhận sai lệch có chủ ý theo đặc thù
domain (ưu tiên **độ chính xác raw HTML extract**), (3) loại bỏ những gì không dùng nữa.

## A. Gate G1 chạy lại — **12/12 PASS**

12 probe cách nhau 60 s, trải 15:21→15:35 UTC:
`https=200` **12/12**, 1.23–1.39 s · `http:80` **RST 12/12** · `robots.txt` **200 12/12**.
Không một lần fail.
→ NSO ổn định trên HTTPS. Chặn ban đầu là chập chờn.
⚠️ Vẫn phải chạy lại **từ máy deploy** trước khi triển khai.

## B. Gate G2 MỞ — design doc đã viết, **chưa viết code**

📄 `project/docs/design/16-periodic-report-scraper.md`

**Phát hiện đổi cục diện: NSO là WordPress có REST API công khai.**
`GET /wp-json/wp/v2/posts?tags=727` — tag 727 = "Báo cáo tình hình kinh tế - xã hội",
**337 bài**, JSON có `date`/`modified` ISO, `slug`, `title`, `content`, `gso_document_type`,
hỗ trợ `after=`/`page=` → incremental sync tự nhiên. Không phải scrape HTML mò như phase-05
giả định ban đầu.

- **Nhịp công bố xác minh:** ngày **3** hàng tháng ~09:00 (2026-09-03 / 08-03 / 07-03).
- **Attachment CHỈ có trên trang HTML render**, không có trong `content.rendered`
  (`acf: []`, `featured_media: 0`) → kiến trúc **lai**: API phát hiện, HTML lấy file.
  `02-Bieu-T8.2026.xlsx` (bảng số liệu) là payload giá trị nhất.
- **robots** cho phép `/wp-json/` và `/wp-content/uploads/`.
- Đề xuất v1: Bronze HTML + Bronze nhị phân, **hoãn** trích XLSX (Bronze là WORM, trích sau
  không cần fetch lại). Cần thêm `RawStore.save_binary()` + bảng `periodic_reports`.
- **5 câu hỏi chờ owner chốt** ở §8 của design doc.

## C. Xoá `enrich_deferred.py` + thay bằng tool Bronze-first

**Đã xoá** `scripts/maintenance/enrich_deferred.py` — nó ghi `content_text` vào DB bằng
`extract_content(http.get(url))`, tức **không tạo Bronze artifact nào**. Dưới Bronze-first đó là
sai nguyên tắc: mọi `content_text` phải truy vết được về một file raw byte-exact.

**Thay bằng** `scripts/maintenance/backfill_deferred.py`:
1. Ưu tiên **thuần**: có Bronze rồi → dựng lại content **từ file đó**, không chạm mạng.
2. Chưa có Bronze + `--fetch` → ghi Bronze **trước** (robots + rate limit + backoff), rồi mới dựng.
3. **Không bao giờ** ghi content nếu không có Bronze tương ứng.

Quy trình 3 bước (đã đưa vào `docs/runbook.md`):
```
refresh_watchlist.py 500 <host>  →  morninger --once derive  →  backfill_deferred.py <host>
```

**Kết quả thật trên vietnambiz:** `verify_quality` **48.8% → 100.0% PASS**
(170/170 bài; title 0 thiếu, body 0 thiếu, date 0 thiếu), 140/140 dựng từ Bronze, 0 fetch mạng.

Cập nhật 6 tài liệu tham chiếu script cũ (`runbook`, `design/06`, `dev/06`, `README`,
`sample_articles.py`, `others/phase1-report`). Thêm `tests/test_backfill_deferred.py` (6 case),
gồm test canh **không cho thêm lại** script Bronze-blind.

## D. Nợ đã đóng so với report gốc

| Mục cũ | Trạng thái |
|---|---|
| #1 Gate G2 NSO | ✅ mở, design doc xong, chờ owner chốt phạm vi |
| #2 Backlog lần đầu — không tool nào đóng trọn | ✅ **đã đóng** bằng `backfill_deferred.py` |
| #8 `.venv` hỏng | ✅ đã sửa từ trước |

Còn mở: #3 review zone TNCK sau 7 ngày · #4 watch TBTC `tbtc-w3` · #5 baodautu 04b (chưa cần,
date-parse 100%) · #6 `vneconomy` thiếu `domains/vneconomy/` · #7 cafef.vn drift + DNS có sẵn.
