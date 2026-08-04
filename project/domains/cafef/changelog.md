# CafeF Domain Changelog

Ghi lại mọi thay đổi của upstream CafeF ảnh hưởng đến scraper.
Cập nhật mỗi khi phát hiện/xác nhận thay đổi.

---

## 2026-08-03 — Domain Mastery Framework

- **Schema contract** được tạo (`schema.yaml`)
- **README mastery** được viết đầy đủ
- **Fixture sample** lưu từ `tests/fixtures/cafef_list_response.json`

## 2026-07-24 — Verification (Phase 1)

- **Verified**: `Type=1` BẮT BUỘC — `Type=2` trả về `Data: []` dù `Success: true`
- **Verified**: `Symbol` và `NewsId` trong response luôn `null`
- **Verified**: `LinkDetail` luôn là relative path, cần `urljoin` với `https://cafef.vn`
- **Verified**: `DeployDate` format `/Date(1784543714000)/` — epoch ms, không có timezone offset
- **Verified**: API cần `Referer: https://cafef.vn/` header
- **Decision**: `PageSize: 20, PageIndex: 1` — không paginate (steady-state cycle 15 phút đủ phủ)
- **Decision**: Detail cap 30/cycle
- **Decision**: Content selector `div#mainContent`

## 2026-07-24 — Initial scraper

- CafeFScraper implemented: symbol-driven API iteration
- `parse_cafef_date()` for `/Date(ms)/` format
- `enrich()` with `div#mainContent` selector + trafilatura extraction
- Test fixtures captured: `cafef_list_response.json`, `cafef_detail_page.html`
