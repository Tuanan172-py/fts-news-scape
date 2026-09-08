---
type: SQLite Table
title: article_versions
description: Log append-only mỗi lần capture 1 URL — fingerprint nội dung/DOM + trạng thái change-detection.
resource: "project/data/monocle.db (table: article_versions)"
tags: [change-detection, silver, versioning, append-only]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore schema DDL
  - id: change-detect
    resource: project/src/pipeline/change_detect.py
    title: Fingerprint + classify 5 trạng thái
  - id: storage-design
    resource: project/docs/design/07-storage-layers-and-change-detection.md
    title: Storage layers & change detection
sources_last_checked: 2026-09-07
---

Bảng `article_versions` là **nhật ký phiên bản** của tầng Silver: mỗi lần một URL được capture
lại, pipeline sinh fingerprint (SHA-256 nội dung, SimHash64, chữ ký đường dẫn DOM) rồi so với
bản trước để phân loại thay đổi.[^change-detect] Append-only — không bao giờ UPDATE hàng cũ.

Bảng này là nguồn của drift report và là căn cứ quyết định một bài có được giao cho agent hay
bị giữ lại (`held`) trong [work_items](work_items.md).

# 5 trạng thái change-detection

| `state` | Điều kiện | `recommendation` |
|---|---|---|
| `NEW` | chưa có bản trước | `re_extract` |
| `UNCHANGED` | `content_sha256` trùng bản trước | `skip` |
| `CONTENT_CHANGED` | sha khác, DOM giữ nguyên | `re_extract` |
| `TEMPLATE_DRIFT` | `dom_path_sig` đổi (trang đổi giao diện) | `manual_review` |
| `SELECTOR_BROKEN` | capture `partial` / thiếu node nội dung chính | `manual_review` |

Hai trạng thái cuối là **held states** — bài không được giao agent cho tới khi người vận hành
sửa selector.[^storage-design]

> Change-detection cần **≥2 lần capture cùng URL**. Chu kỳ thường chỉ capture bài mới, nên muốn
> kích hoạt phải chạy `scripts/refresh_watchlist.py` để chủ động re-fetch URL đã biết.

# Schema

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | |
| `url_title_hash` | TEXT NOT NULL | `article_id` — khoá xuyên tầng |
| `source_domain` | TEXT | Tên miền nguồn |
| `captured_at` | TEXT | Thời điểm bản capture này |
| `content_sha256` | TEXT | SHA-256 của raw bytes = `raw_sha256` (khoá provenance) |
| `simhash64` | TEXT | SimHash 64-bit của văn bản (đo thay đổi mềm) |
| `dom_path_sig` | TEXT | Chữ ký cấu trúc DOM |
| `capture_status` | TEXT | `ok` / `partial` / `failed` |
| `prev_version_id` | INTEGER | Trỏ bản trước (self-reference) |
| `hamming_content` | INTEGER | Khoảng cách Hamming SimHash so bản trước |
| `dom_changed` | INTEGER | 1 nếu `dom_path_sig` đổi |
| `selector_drift` | INTEGER | 1 nếu selector nội dung không khớp |
| `state` | TEXT | 1 trong 5 trạng thái ở trên |
| `recommendation` | TEXT | `re_extract` / `skip` / `manual_review` |

**Indexes:** `idx_versions_hash` trên `(url_title_hash, captured_at)` ·
`idx_versions_state` trên `(state, captured_at)`

# Common Query Patterns

### Bài cần người xem lại (drift)

```sql
SELECT url_title_hash, source_domain, state, captured_at
FROM article_versions
WHERE state IN ('TEMPLATE_DRIFT', 'SELECTOR_BROKEN')
  AND captured_at >= datetime('now', '-7 days', 'localtime')
ORDER BY captured_at DESC;
```

### Phân bố trạng thái theo domain (24h)

```sql
SELECT source_domain, state, COUNT(*) AS n
FROM article_versions
WHERE captured_at >= datetime('now', '-1 day', 'localtime')
GROUP BY source_domain, state
ORDER BY source_domain, n DESC;
```

# Joins

- [articles](articles.md) qua `url_title_hash`
- [work_items](work_items.md) qua `url_title_hash = article_id` **và** `content_sha256 = raw_sha256`

# Pipeline liên quan

- Sinh bởi [Silver Derive](../pipelines/silver_derive.md)

[^db-store]: [ArticleStore schema DDL](project/src/db/store.py)
[^change-detect]: [change_detect.py](project/src/pipeline/change_detect.py)
[^storage-design]: [Storage layers & change detection](project/docs/design/07-storage-layers-and-change-detection.md)
