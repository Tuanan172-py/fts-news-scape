# Domain Report — vietnambiz (2026-09-07)

## vietnambiz.vn

- **Articles today**: 170 new
- **Articles in DB**: 170
- **Sources**: vietnambiz.vn

### Field Health

| Field | Fill Rate | Avg Length | Status |
|------|-----------|-----------|--------|
| url | 100% | 109 | **OK** |
| title | 100% | 69 | **OK** |
| source_domain | 100% | 13 | **OK** |
| published_at | 100% | 25 | **OK** |
| summary | 100% | 191 | **OK** |
| content_text | 100% | 706 | **OK** |
| content_html | 18% | 5184 | **WARN** |
| symbols | 12% | 3 | **WARN** |
| categories | 100% | 28 | **OK** |
| metadata.language | 100% | — | **OK** |
| metadata.capture | 18% | — | **FAIL** |

### Watch Points

- **[HIGH]** `vnb-w1` — Đổi class body → _looks_complete=False → capture_status=partial → SELECTOR_BROKEN → agent HOLD bài. Đây là watch point số 1.
- **[LOW]** `vnb-w2` — Feed khai utf-16 serve utf-8; nếu sửa đúng thành utf-8 thì _decode_feed vẫn chạy (no-op).
- **[MEDIUM]** `vnb-w3` — Format phi chuẩn; _parse_raw_date normalize GMT+7→+0700. Format lạ → published_at rỗng.
- **[MEDIUM]** `vnb-w4` — 1 feed chết → error, feed khác vẫn chạy (per-feed isolation). quoc-te.rss đã chết.
- **[LOW]** `vnb-w5` — Nếu đổi sang .html thì url_title_hash đổi → toàn bộ bài cũ bị coi là mới 1 lần.
- **[HIGH]** `vnb-w6` — Hiện Allow: / hoàn toàn. Nếu thêm Disallow cho article path → RobotsGate chặn, capture_status=skipped_robots.

### Recent Anomalies

*None*

---
**Overall: 0 critical, 0 warnings, 1 failed fields**
