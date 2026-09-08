# FireAnt Domain Changelog

## 2026-09-07 — Bật lại + nâng cấp Bronze capture (JSON)

**Thay đổi**
- `enabled: false → true` (tắt 2026-08-03 "focus cafef+vietstock").
- `method: api → fireant`; `FireAntScraper` giờ kế thừa `CaptureMixin`.
- Bronze = **body JSON của API detail**, lưu byte-exact qua `RawStore.save()`.
- `SilverBuilder` thêm nhánh generic: thấy `Content-Type: application/json` thì bóc
  trường HTML (`_html_from_json`) trước khi trích — nếu không, `cleaned_text` sẽ nuốt
  cả key/dấu ngoặc JSON.
- Tạo `domains/fireant/{schema.yaml,changelog.md,README.md}`.
- `tests/test_fireant.py`: 6 → **11 case** (thêm Bronze byte-exact, Silver bóc JSON,
  camelCase regression, 401 không ghi Bronze, content rỗng → partial).

**Hai bug thật đã sửa (tồn tại từ trước)**
1. **`post_source` vs `postSource`** — API trả **camelCase**, code cũ đọc snake_case
   → `metadata.source_name`/`source_url` **LUÔN rỗng**. Có test regression.
2. **Permalink sai** — `WEB_URL` cũ là `/bai-viet/{id}` → **404**. Đúng là
   `/dashboard/content/{id}` (verified 2026-09-07). `article.url` là định danh
   (`url_title_hash`) nên sửa được vì DB chưa có row fireant nào.

**Vì sao Bronze là JSON chứ không phải HTML**
`fireant.vn/dashboard/content/{id}` là Next.js SPA (`__NEXT_DATA__`, `<div id="__next">`);
body bài không có trong HTTP GET. Nguồn sự thật duy nhất là response API.
→ KHÔNG dùng `_capture_and_extract` (nó chạy CSS selector nên báo `partial` oan cho mọi bài);
gọi thẳng `RawStore.save()`.

**Verified live 2026-09-07**
- Token trong `secrets.yaml` còn hạn (JWT exp 2036); list + detail đều HTTP 200.
- `diagnose_sources.py fireant`: **fetched=600** (30 mã × 20), enrich 2/2 ok, **0 lỗi**.
- `--once fireant`: **493 bài mới**, 30 Bronze artifact.
- List `content` rỗng → bắt buộc gọi detail (`content` ~3.7k HTML).
- Ảnh trên `static.fireant.vn`. `date` đã ISO +07:00.

**⚠️ TUÂN THỦ — CẦN OWNER XÁC NHẬN**
`robots.txt` của **fireant.vn** (2026-09-07):
```
User-agent: *
Content-Signal: search=yes, ai-train=no, use=reference
Allow: /
User-agent: ClaudeBot   → Disallow: /
User-agent: GPTBot      → Disallow: /
User-agent: CCBot / Google-Extended / Amazonbot / Bytespider / ... → Disallow: /
```
- Site **chặn tường minh** các crawler AI và khai **`ai-train=no`**.
- Ta **không** crawl website ẩn danh: ta gọi `restv2.fireant.vn` (**không có robots.txt**)
  bằng **token của chính người dùng** → chịu ràng buộc **ToS tài khoản**, không phải robots
  dành cho crawler.
- **Luật cứng:** TUYỆT ĐỐI không dùng dữ liệu fireant để huấn luyện/fine-tune model.
- Owner nên rà lại ToS tài khoản FireAnt xem có cho phép truy xuất tự động hay không.
  Nếu không → tắt lại `enabled: false`.

## 2026-08-03 — Disabled
Tắt cùng ~20 domain khác khi hệ thống chuyển sang Bronze-first.

## 2026-07-26 — Fix endpoint
`/post/{id}` (số ít) trả 404 → đúng là `/posts/{id}` (số nhiều).

## 2026-07-24 — Verification (Phase 1)
Bearer token bắt buộc (401 nếu thiếu). Token hết hạn → self-disable + ERROR log.
