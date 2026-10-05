# Report 04 — NSO (G2 v1) + FireAnt, 2026-09-07 (phiên 3)

Owner duyệt 4 việc: (1) chấp nhận cảnh báo git 2 luồng, (2) **viết code hoàn chỉnh NSO**,
(3) xoá những gì không dùng, (4) **mở fireant** + enable các domain vừa test.

`pytest -q` = **345 passed, 0 failed** (đầu phiên 310). Domain enabled: **7 → 8**.

---

## 1. NSO — Gate G2 v1 ĐÃ TRIỂN KHAI + validate LIVE

### Đã build

| File | Vai trò |
|---|---|
| `src/pipeline/periodic_reports.py` | `PeriodicReportSource` + `parse_period()` + `extract_attachments()` |
| `scripts/fetch_periodic_reports.py` | CLI: `--after --limit --dry-run --no-attachments --list` |
| `src/crawler/raw_store.py` → **`save_binary()`** | Bronze nhị phân (.xlsx/.docx/.pdf) — ghi bytes, KHÔNG parse |
| `src/db/store.py` → bảng **`periodic_reports`** | `UNIQUE(source, report_type, period, revision)` |
| `tests/test_periodic_reports.py` | **21 case** |

**Giữ đúng thiết kế — KHÔNG có:** `config/domains/nso.yaml`, `src/scrapers/nso.py`,
đăng ký `REGISTRY`, headless browser. NSO **không** là domain thứ 25.

### Validate LIVE

```
--dry-run --per-page 12  → discovered=12, 12/12 parse đúng kỳ, 0 held
                           (monthly 2026-08/07/05/04/02/01 + quarterly 2026-Q2/Q1/2025-Q4/Q3…)

--limit 3                → captured=3 revised=0 skipped_unchanged=0
                           held_unparsed=0 failed=0 attachments=6

--limit 3  (chạy lại)    → captured=0 skipped_unchanged=3        ← IDEMPOTENT
```

Bronze thật:
```
data/raw_html/nso.gov.vn/20260907/
  monthly-2026-08-r1.html                            116 KB
  monthly-2026-08-r1__01-Loi-van-T8.2026-final.docx  1.4 MB
  monthly-2026-08-r1__02-Bieu-T8.2026.xlsx           867 KB  ← BẢNG SỐ LIỆU
  monthly-2026-07-r1.*   quarterly-2026-Q2-r1.*      (+ .meta.json mỗi file)
```

**XLSX mở được thật:** `zipfile.is_zipfile()` → True, có `xl/worksheets/sheet4..7.xml`,
`sha256` khớp `.meta.json`, `capture_status: ok`.

### Bất biến được test khoá (21 case)

- **dedup theo `(report_type, period)`** — test dùng slug **sai năm + hậu tố `-2`** (đúng
  như NSO thật) và `id` khác → vẫn `skipped_unchanged`, **không fetch lại trang**.
- `modified` đổi → **revision mới**, bản cũ còn nguyên (`r1` + `r2` cùng tồn tại).
- Không parse được kỳ → **held + error**, không capture, không ghi DB, **không đoán bừa**.
- Attachment byte-exact + sha256 khớp.
- `discover` lỗi HTTP 503 → summary rỗng + error, **không raise**.
- `parse_period` phủ 11 dạng tiêu đề (tháng chữ/số, quý La Mã, thiếu năm → None).

### Hai bug tự tìm khi validate

1. **Đuôi file lặp `.xlsx.xlsx`** — `_safe_key` giữ cả đuôi trong khi `save_binary` tự gắn
   đuôi theo Content-Type. → bỏ đuôi trong key. Có test.
2. **Mất case tên file** — `extract_attachments` hạ chữ cả path để so đuôi nên
   `02-Bieu-T8.2026.xlsx` → `02-bieu-t8.2026.xlsx`. → chỉ hạ chữ khi **so khớp**. Có test.

### Hoãn sang v2 (đúng chủ ý, YAGNI)

Trích số liệu XLSX → JSON/CSV; bản `/en/`; series CPI/IIP/FDI/XNK/bán lẻ; Silver cho báo cáo.
Bronze là WORM nên trích lúc nào cũng được, **không cần fetch lại**.

---

## 2. FireAnt — bật lại + nâng cấp Bronze

### ⚠️ Bronze của nguồn này là **JSON**, không phải HTML

`fireant.vn/dashboard/content/{id}` là **Next.js SPA** — body bài không có trong HTTP GET.
Nguồn sự thật duy nhất là **response API detail** (`content` = HTML thân bài).

→ `enrich()` gọi thẳng `RawStore.save()` (byte-exact). **KHÔNG** dùng
`CaptureMixin._capture_and_extract`: hàm đó chạy CSS selector (`_looks_complete`) nên sẽ
gắn `partial` **oan** cho 100% số bài.

→ Thêm nhánh **generic** vào `SilverBuilder`: thấy `Content-Type: application/json` thì bóc
trường HTML qua `_html_from_json()` trước khi trích. Nhận diện theo **ĐỊNH DẠNG**, không
phải luật riêng domain (giữ module generic — design 12). Không có bước này, `cleaned_text`
sẽ nuốt cả key JSON và dấu ngoặc.

### Hai bug thật tồn tại từ trước — đã sửa

1. **`post_source` vs `postSource`** — API trả **camelCase**, code cũ đọc snake_case
   → `metadata.source_name`/`source_url` **LUÔN rỗng**. Có test regression.
2. **Permalink sai** — `/bai-viet/{id}` trả **404**; đúng là `/dashboard/content/{id}`.
   Sửa được vì DB chưa có row fireant nào (URL là định danh `url_title_hash`).

### Validate LIVE

```
diagnose_sources.py fireant → fetched=600 (30 mã × 20), enrich 2/2 ok, 0 LỖI
--once fireant              → 493 bài mới, 30 Bronze artifact
```
Token trong `secrets.yaml` còn hạn (JWT exp 2036), list + detail đều HTTP 200.
`tests/test_fireant.py`: 6 → **11 case**.

### 🔴 TUÂN THỦ — CẦN OWNER XÁC NHẬN

`robots.txt` của **fireant.vn** (2026-09-07):
```
User-agent: *
Content-Signal: search=yes, ai-train=no, use=reference
Allow: /
User-agent: ClaudeBot  → Disallow: /       (cùng GPTBot, CCBot, Google-Extended,
User-agent: GPTBot     → Disallow: /        Amazonbot, Bytespider, meta-externalagent…)
```

- Site **chặn tường minh** crawler AI và khai **`ai-train=no`**.
- Nhưng ta **không crawl website ẩn danh**: ta gọi `restv2.fireant.vn`
  (**không có robots.txt** — 404) bằng **token của chính người dùng** → quan hệ ở đây là
  **ToS/thoả thuận tài khoản**, không phải robots dành cho crawler.
- **Luật cứng đã ghi vào code + docs:** TUYỆT ĐỐI không dùng dữ liệu fireant để
  huấn luyện/fine-tune model. Phân tích nội bộ khớp với `use=reference` mà site khai.

**Việc của owner:** rà ToS tài khoản FireAnt xem có cho phép truy xuất tự động không.
Nếu không → đặt lại `enabled: false`. Watch point `fa-w5` theo dõi robots đổi.

Tôi đã bật theo yêu cầu, nhưng đây là thông tin **mới** phát hiện khi làm — anh nên biết
trước khi chốt.

---

## 3. Dọn dẹp + hoàn thiện

- `.gitignore`: thêm `**/data/reports/` (report ngày là output chạy máy).
- `domains/fireant/{schema.yaml,README.md,changelog.md}` — mới.
- **8/8 domain enabled đều có contract hợp lệ** (đã thêm `vneconomy` ở phiên trước).
- Docs: `docs/domains/README.md` (ma trận + đếm 7→8 + ghi chú NSO ngoài ma trận),
  `api-scrapers.md` (section fireant viết lại), `runbook.md` (+ mục NSO),
  `design/16` (+ §9 kết quả triển khai), `README.md` gốc.

---

## 4. Trạng thái nguồn cuối phiên

**8 enabled** — tất cả đều có Bronze capture:
cafef · vietstock · vneconomy · vietnambiz · thoibaotaichinhvietnam · tnck · baodautu · **fireant**

**Ngoài ma trận:** NSO (báo cáo KTXH định kỳ) — driver riêng, dedup theo `(type, period)`.

Bronze dirs: 9 (8 domain + `nso.gov.vn`).

---

## 5. Việc còn mở

| # | Việc | Ai |
|---|---|---|
| 1 | **ToS FireAnt** — xác nhận truy xuất tự động được phép | owner |
| 2 | Chạy `fetch_periodic_reports.py --dry-run` **từ máy deploy** (NSO từng chập chờn) | owner |
| 3 | Gắn cron NSO hay chạy tay hàng tháng | owner |
| 4 | NSO v2: trích số liệu XLSX → JSON/CSV | hoãn |
| 5 | TNCK zone 8/13/36/43 — review sau 7 ngày | theo lịch |
| 6 | cafef.vn: 2 SELECTOR_BROKEN từ 2026-09-04 + lỗi DNS trong log | có sẵn |
| 7 | ⚠️ **git 2 luồng** — xem `reports/03-files-changed.md`, ĐỪNG `git add -A` | owner |

## 6. Câu hỏi chưa giải

- NSO: có cần Silver cho báo cáo định kỳ không, hay Bronze + hàng DB là đủ?
- fireant: 600 request list/cycle (30 mã) có quá dày với site không? Cân nhắc giảm watchlist
  hoặc giãn nhịp riêng cho nguồn này.
- fireant trùng nội dung với cafef/vietstock (cùng aggregate báo gốc) — fuzzy dedup
  cross-domain đã bật, nhưng nên đo tỉ lệ trùng thực tế sau 1 tuần.


---

## 7. Backfill backlog + 2 lỗi tự tìm trong tool của chính mình

Sau khi chạy backfill cho tnck/baodautu, `verify_quality` lộ ra **lỗi trong
`backfill_deferred.py` mà tôi vừa viết**:

### Lỗi 1 — không khôi phục `published_at`
baodautu: body 0 thiếu nhưng **date thiếu 79/109** → 27.5%.
Nguyên nhân: tool chỉ dựng lại `content_text`, **không đụng `published_at`**. Với baodautu,
ngày CHỈ có ở trang detail (không `<time>`, không `article:published_time`, không JSON-LD —
là text thuần trong `span.post-time`), mà bài deferred **chưa từng qua `enrich()`** nên cột rỗng.

**Sửa:** thêm `recover_published_at()` — thứ tự generic trước, config sau:
`meta[article:published_time]` → `meta[datePublished]` → `<time datetime>` → JSON-LD →
`detail.date_scope_selector` + regex `dd/MM/yyyy HH:mm`. Không khớp → **rỗng, không bịa**.
Thêm chế độ `--dates-only` để sửa riêng cột ngày cho bài đã gỡ cờ deferred.

→ **baodautu 27.5% → 99.1% PASS** (78/79 khôi phục được; 1 bài thật sự không có ngày trên trang).

### Lỗi 2 — regex bị hỏng bởi heredoc
`` trong heredoc bash bị biến thành ký tự **backspace ``** → regex khớp ký tự điều khiển,
không bao giờ match. `date_recovered=0` dù Bronze có sẵn `span.post-time`.
Phát hiện bằng `repr(pattern)`. Sửa bằng script riêng (tránh mọi lớp escape của shell).
**Bài học:** đừng sửa regex qua heredoc — dùng file script hoặc Edit tool.

### Lỗi 3 — backfill không hiểu Bronze JSON / endpoint API
fireant: Bronze là **JSON** và `articles.url` là trang **SPA** → backfill sẽ (a) nuốt key JSON
vào `content_text`, (b) `--fetch` sẽ tải nhầm trang SPA rỗng.

**Sửa:**
- `_extract_from_bronze` dùng lại `_html_from_json` của `SilverBuilder` → bóc trường HTML.
- `_detail_endpoint()` đọc `api.detail_url_template` + `metadata` để dựng URL **API**,
  kèm Bearer token từ `auth.secret_key`. Config-driven, không hardcode fireant.

`tests/test_backfill_deferred.py`: 6 → **11 case**.

---

## 8. Chất lượng cuối phiên (`verify_quality`)

| Nguồn | Trước | Sau | Ghi chú |
|---|---|---|---|
| **vietnambiz.vn** | 48.8% | **100.0% PASS** | 170/170 |
| **baodautu.vn** | 27.5% | **99.1% PASS** | 78/79 ngày khôi phục; 1 bài thật sự không có ngày |
| **thoibaotaichinhvietnam.vn** | — | **95.8% PASS** | 1 bài body ngắn |
| **tinnhanhchungkhoan.vn** | 48%* | **92.1%** ⚠️ | 314 backfill OK. 28 bài còn lại **ngắn hợp lệ** — bố cáo ĐHCĐ kiểu *"CTCP Thép Pomina (POM – UpCoM)"* ~116 ký tự. **Không phải lỗi**; ngưỡng 200 ký tự không hợp với zone 29/28 |
| **fireant.vn** | 27.7% | *(đang backfill)* | 258 bài deferred, fetch qua API |

\* tnck trước backfill.

**Đề xuất:** `verify_quality` nên cho phép ngưỡng `min_body` theo domain — tnck có zone
"Đại hội cổ đông"/"Thông báo - bố cáo" mà bài **đúng là** vài dòng. Ép 200 ký tự cho mọi
nguồn sẽ mãi FAIL oan. (Chưa sửa — cần owner quyết.)
