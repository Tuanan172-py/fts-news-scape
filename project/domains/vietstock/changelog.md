# Vietstock Domain Changelog

Ghi lại mọi thay đổi của upstream Vietstock ảnh hưởng đến scraper.
Cập nhật mỗi khi phát hiện/xác nhận thay đổi.

---

## 2026-08-03 — Domain Mastery Framework

- **Schema contract** được tạo (`schema.yaml`)
- **README mastery** được viết đầy đủ
- **Fixture sample** lưu từ `tests/fixtures/vietstock_feed.xml`

## 2026-07-24 — Verification (Phase 1)

- **Verified**: Internal API (TopPageArticle...) không dùng được — cần browser session → RSS primary
- **Verified**: 4 feeds active: tin-moi, chung-khoan, doanh-nghiep, vi-mo
- **Verified**: `pubDate` format `Fri, 24 Jul 2026 14:54:34 +0700`
- **Verified**: `description` chứa `<img>` tags — cần extract_text qua trafilatura
- **Verified**: `content:encoded` KHÔNG có trong feed
- **Decision**: `extract_full: true, max_details_per_cycle: 30`
- **Decision**: Không dùng filter — tất cả entries từ 4 feeds đều có giá trị
- **Decision**: encoding detection multi-stage (UTF-16 BOM, null bytes, utf-8-sig)

## 2026-07-25 — Phase 2 Integration

- **Added**: `_parse_raw_date()` với fallback cho GMT+7, +07, US format, narrow no-break space
- **Added**: `link_rewrites` support (Vietstock không cần, nhưng framework hỗ trợ)
- **Test fixture**: `vietstock_feed.xml` captured (28+ items, 2 intentional duplicates)

## 2026-07-26 — Phase 2 Hardening

- **Fixed**: `+07` → `+0700` regex fix trong `_parse_raw_date` (không corrupt well-formed `+0700`)
- **Added**: Date validation cho pubDate parsed từ feedparser struct_time
