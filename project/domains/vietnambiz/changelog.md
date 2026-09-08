# VietnamBiz Domain Changelog

Ghi lại mọi thay đổi của upstream VietnamBiz ảnh hưởng đến scraper.
Cập nhật mỗi khi phát hiện/xác nhận thay đổi.

---

## 2026-09-07 — Re-enable + chuyển sang Bronze capture (phase-01)

Kế hoạch: `plans/20260907-0834-market-sources-expansion/phase-01-rss-capture-framework-vietnambiz.md`

**Thay đổi**
- `enabled: false` → `true` (disabled từ 2026-08-03 "focus cafef + vietstock").
- `method: rss` → **`rss_capture`** — nguồn đầu tiên chạy class mới
  `RssCaptureScraper` (`src/scrapers/rss_capture.py`, kế thừa `RSSScraper`).
  Lý do: `method: rss` **không lưu Bronze** (`RSSScraper.enrich` không gọi `RawStore`).
- Feeds 3 → **6**: thêm `doanh-nghiep.rss`, `nha-dat.rss`, `hang-hoa.rss`.
- Thêm block `capture` + `compliance` + `base_url` + `content_selector`.
- Tạo `domains/vietnambiz/{schema.yaml,README.md,changelog.md}`.

**Verified live (curl, 2026-09-07)**
- 6/7 feed trả HTTP 200 với **30 `<item>`** mỗi feed.
- `quoc-te.rss` → 200 nhưng **0 item / 356 bytes** → CHẾT, không đưa vào config.
- `robots.txt` = `User-agent: * / Allow: /` — không `Disallow`, không `Crawl-delay`.
- XML declaration vẫn khai `encoding="utf-16"` trong khi serve utf-8 (quirk cũ còn nguyên).
- `pubDate` dạng `Mon, 07 Sep 2026 19:41:53 GMT+7`.
- Article URL đuôi `.htm`.
- Ảnh trên `cdn.vietnambiz.vn`, `src` trực tiếp (không lazy-load).

**Phát hiện quan trọng — trang detail KHÔNG có thẻ `<article>`**
Kế hoạch ban đầu định "ship không có `content_selector`, dựa vào density fallback".
Audit (`reports/01-plan-audit-report.md` §A2) chứng minh điều đó **SAI**:
`CaptureMixin._looks_complete()` trả `False` khi selector không khớp →
`capture_status = "partial"` + `missing[incomplete_render]` →
`change_detect.classify()` = **`SELECTOR_BROKEN`** → `manual_review` → **agent HOLD bài**.
`_density_extract` chỉ vá `content_html`, **không** vá `capture_status`.
→ `content_selector` là BẮT BUỘC. Đã xác minh và chốt: **`div.vnbcbc-body`**.
→ Có test regression `test_default_article_selector_would_break`.

**Selector chốt**
- Body: `div.vnbcbc-body` (`.vnbcbc-body.vceditor-content[data-role=content]`).
- KHÔNG dùng `div.post-body-content` — bọc cả title/author/date.
- Title: `h1.vnbcb-title`. Ngày (tham chiếu): `span.vnbcbat-data[data-role=publishdate]`.

**Bẫy mới ghi nhận**
`<meta property="article:published_time" content="2026-09-07T19:41:00">` **thiếu offset
timezone**. Vô hại hiện tại vì `_parse_entry_date` đọc `pubDate` của RSS trước —
nhưng **đừng** "tối ưu" bằng cách chuyển sang meta tag.

**Test**: `tests/test_rss_capture.py` — 10 case, pass.
Fixtures: `tests/fixtures/vietnambiz_capture_feed.xml` (3 item, giữ nguyên khai báo utf-16),
`tests/fixtures/vietnambiz_detail_page.html` (bài thật, 112.472 bytes).

## 2026-08-03 — Disabled

Tắt cùng ~20 domain khác ("focus on cafef + vietstock only"). Không phải vì nguồn hỏng —
mà vì hệ thống chuyển sang Bronze-first: mỗi nguồn phải có full raw HTML capture, nên cần
research riêng từng trang thay vì mở rộng theo RSS như trước.

## 2026-07-25 — Verification (Phase 2)

- **Verified**: 3 feed `chung-khoan` / `tai-chinh` / `vi-mo`, 30 items/zone.
- **Verified**: XML declaration khai `utf-16` nhưng serve utf-8 bytes →
  `_decode_feed` strip encoding attr khỏi 200 byte đầu.
- **Verified**: brotli bytes rác nếu HTTP client tự khai `Accept-Encoding` →
  `http_client.py` cố tình không khai.
