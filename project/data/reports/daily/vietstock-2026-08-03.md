# Domain Report — vietstock (2026-08-03)

## vietstock.vn

- **Articles today**: 96 new
- **Articles in DB**: 96
- **Sources**: vietstock.vn

### Field Health

| Field | Fill Rate | Avg Length | Status |
|------|-----------|-----------|--------|
| url | 100% | 112 | **OK** |
| title | 100% | 69 | **OK** |
| source_domain | 100% | 12 | **OK** |
| published_at | 100% | 25 | **OK** |
| summary | 100% | 243 | **OK** |
| content_text | 100% | 1856 | **OK** |
| content_html | 32% | 391742 | **OK** |
| author | 0% | — | **OK** |
| symbols | 11% | 4 | **WARN** |
| categories | 100% | 28 | **OK** |
| metadata.feed_name | 100% | — | **OK** |
| metadata.language | 100% | — | **OK** |

### Watch Points

- **[MEDIUM]** `vs-w1` — 1 feed URL thay đổi → feed đó chết, các feed khác vẫn chạy (per-feed isolation)
- **[LOW]** `vs-w2` — pubDate format thay đổi → _parse_entry_date có multiple fallback parsers (GMT+7, +07, US format). Unknown format → published_at rỗng
- **[LOW]** `vs-w3` — Description thay đổi cấu trúc HTML → extract_text vẫn hoạt động (strip HTML tags)
- **[LOW]** `vs-w4` — Title double-encoded entities thay đổi → _clean_title() xử lý html.unescape()
- **[LOW]** `vs-w5` — Feed đổi encoding → _decode_feed() có multi-stage detection (UTF-16 BOM, null bytes, utf-8-sig)
- **[MEDIUM]** `vs-w6` — trafilatura không extract được detail page → fallback summary

### Recent Anomalies

*None*

---
**Overall: ALL OK**
