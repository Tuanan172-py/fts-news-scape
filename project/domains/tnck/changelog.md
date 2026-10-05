# TNCK Domain Changelog

Ghi lại mọi thay đổi upstream của tinnhanhchungkhoan.vn ảnh hưởng đến scraper.

---

## 2026-09-07 — Nâng cấp Bronze capture + mở rộng zone (phase-03)

Kế hoạch: `plans/20260907-0834-market-sources-expansion/phase-03-tnck-capture-upgrade.md`

**Vấn đề gốc:** `TnckScraper` chạy được nhưng **KHÔNG dùng `CaptureMixin`** — `enrich()` gọi
thẳng `http.get()` + `extract_content()`, **không ghi Bronze artifact nào**, không robots gate,
không backoff, không `.meta.json`, và **thiếu `metadata["language"]`**.

**Thay đổi**
- `src/scrapers/tnck.py` → `class TnckScraper(CaptureMixin, BaseScraper)`, `_init_capture()`,
  `enrich()` dùng `_capture_and_extract`. Bỏ `ZoneInfo` cục bộ, dùng `src.core.models.VN_TZ` (DRY).
- Thêm `metadata["language"]` và `metadata["zone_id"]`.
- `config/domains/tnck.yaml`: `enabled: true`, zone **1 → 9**, `pages_per_cycle: 2 → 1`,
  thêm `content_selector` / `capture` / `compliance` / `base_url`, sửa lại `pitfalls`.
- `domains/tnck/{schema.yaml,README.md,changelog.md}` mới.
- `tests/test_tnck.py` viết lại — 13 case.

**Sửa bẫy `.vn`-suffix (ảnh hưởng toàn repo)**
`scripts/domain_check.py:152` và `src/monitor/domain_reporter.py:126,170` dùng
`f"{dom}.vn" if "." not in dom else dom` → tên config `tnck` biến thành `tnck.vn`,
**không khớp gì trong DB** → báo "0 articles" / anomaly giả.
→ Thêm `resolve_source_domain(name)` vào `src/core/config.py`, ưu tiên
`domains/<name>/schema.yaml` → `domain:`, rồi `base_url` netloc, cuối cùng mới fallback
legacy `<name>.vn`. Wire vào cả 3 call site. TNCK là nguồn đầu tiên có `name != host stem`.

**Quyết định `source_domain` — NON-WWW**
Chốt `tinnhanhchungkhoan.vn` (không www), khớp quy ước `removeprefix("www.")` toàn repo.
Kiểm tra DB trước khi chốt: **không có row TNCK nào tồn tại** (`articles.source_domain` chỉ có
cafef.vn/vietstock.vn/vneconomy.vn) → không có rủi ro đứt gãy dedup.
`article.url` **giữ nguyên host www** mà API trả về — đổi URL sẽ đổi `url_title_hash`,
tức đổi định danh bài.
Hệ quả: Bronze partition `data/raw_html/tinnhanhchungkhoan.vn/`,
và `scripts/verify_quality.py tinnhanhchungkhoan.vn` (dùng HOST, không phải `tnck`).

**Zone map — quét đầy đủ 1..45 (verified 2026-09-07)**
Bật 9 zone: `[1, 4, 6, 11, 21, 26, 29, 33, 39]` = Chứng khoán, Thông tin doanh nghiệp,
Tiền tệ, Trái phiếu, Pháp luật, M&A, Đại hội cổ đông, Pháp đình, Vĩ mô.

⚠️ **Zone 8 "Điều tra" bị LOẠI khỏi v1** dù tên rất hợp beat "điều tra doanh nghiệp".
Lý do: nội dung thực tế **lệch sang hình sự/tiêu dùng chung** (mẫu 2026-09-07:
"Bộ Công an: Huấn...", "Fanpage tích xanh giả mạo cơ sở lưu trú", "Bến thủy nội địa không phép").
Tín hiệu pháp lý doanh nghiệp thật nằm ở zone **21/33/26/29**. Quyết lại sau 7 ngày đo.

Loại vĩnh viễn: 27/45/32 (PR trả tiền), 14 (item không có object `zone`),
16 (thông báo báo in VIR), 10 (Tòa soạn, 3 item), 15/18/19/20 (rỗng), và các zone trùng
(12↔9, 24↔3, 34↔1, 35↔7, 38↔30, 42↔2).

**Sửa sai trong tài liệu cũ**
`date` là **JSON NUMBER** (epoch giây), không phải string như `docs/skills/tnck.md` và
`pitfalls` cũ ghi. `int()` nhận cả hai nên không có bug thực tế, nhưng docs đã sai.
Có test `test_epoch_number_and_string` canh chừng.

**Verified live 2026-09-07**
- KHÔNG có RSS: `/rss.html` = 200 nhưng **13 bytes**; `/rss/trang-chu.rss`,
  `/chung-khoan.rss`, `/rss/chung-khoan.rss` = **302 + 0 byte**. API zone là route duy nhất.
- Response `Content-Encoding: gzip`, `application/json;charset=utf-8`, `Server: WT_11.11`.
- robots www: Disallow `/api/` — nhưng **`api.tinnhanhchungkhoan.vn` là HOST KHÁC**
  (robots riêng, 200 rỗng). Bài `/<slug>-post<NNN>.html` được phép. Không khai `Crawl-delay`.
- Detail server-rendered, body `div.article__body.cms-body`,
  `article:published_time` = `2026-09-07T17:52:56+0700`.
- ⚠️ Quảng cáo `div[id^=adsWeb_]` nằm **BÊN TRONG** body → sẽ lọt vào Silver `cleaned_text`.
  Strip ở Silver nếu nhiễu; **không đụng Bronze**.

## 2026-08-03 — Disabled

Tắt cùng ~20 domain khác ("focus on cafef + vietstock only") khi hệ thống chuyển sang Bronze-first.

## 2026-07-24 — Verification (Phase 1)

- **Verified**: endpoint zone API, `data.contents[]` 40 item/page.
- **Verified**: `phrase` param BỊ IGNORE (phrase=HPG trả y hệt zone content).
- **Decision**: tag ticker client-side qua `core/tickers.py`.
