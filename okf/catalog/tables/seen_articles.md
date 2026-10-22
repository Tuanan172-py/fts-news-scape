---
type: SQLite Table
title: seen_articles
description: Cache khử trùng lặp — hash SHA-256(url+title) đã đi qua pipeline, tra trực tiếp trong SQLite.
resource: "<DATA_ROOT>/monocle.db (table: seen_articles)"
tags: [deduplication, sqlite, internal]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: dedup
    resource: project/src/db/dedup.py
    title: DedupCache — exact hash + sổ phát hiện URL
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore schema DDL
  - id: data-model
    resource: project/docs/dev/02-data-model-and-db.md
    title: Data Model & DB Design
sources_last_checked: 2026-10-22
---

Bảng `seen_articles` là lớp dedup **exact** của capture. Mỗi bài đi qua pipeline sinh 1 hash
SHA-256(`url` + `title`); hash đã có ⇒ bỏ qua, không fetch trang chi tiết, không ghi
[articles](articles.md).[^dedup]

Cơ chế:[^dedup]
1. **Exact** — `DedupCache.is_duplicate()` tra `seen_articles.hash` bằng một `SELECT` trên SQLite;
   `articles.url_title_hash` UNIQUE là chốt cuối.
2. **Định danh URL** — `DedupCache.discover()` ghi sổ phát hiện `discovered_urls` / `url_aliases`
   (ADR 0013) trước mọi bước lọc; biến thể URL quy về cùng `url_canonical` (`src/core/urlnorm.py`).

Không có lớp so tiêu đề mờ: `title_norm` được lưu nhưng không dùng để loại trùng. File
`dedup_cache.json` cũ chỉ còn được đọc một lần để chuyển vào bảng.

# Schema

| Column | Type | Constraints | Description |
|---|---|---|---|
| `hash` | TEXT | PRIMARY KEY | SHA-256(`url` + `title`) |
| `title_norm` | TEXT | | Tiêu đề đã normalize (`normalize_title`) |
| `source_domain` | TEXT | | Tên miền nguồn |
| `seen_at` | REAL | | Epoch seconds thời điểm đánh dấu |

**Index:** `idx_seen_source` trên `(source_domain, seen_at)`

⚠️ Khoá chính tên là `hash` (KHÔNG phải `hash_id`) và `seen_at` là **REAL epoch**, không phải
chuỗi ISO như các bảng khác.

# Common Query Patterns

### Số hash đã thấy theo nguồn trong 24h

```sql
SELECT source_domain, COUNT(*) AS seen
FROM seen_articles
WHERE seen_at >= strftime('%s', 'now', '-1 day')
GROUP BY source_domain
ORDER BY seen DESC;
```

# Joins

- [articles](articles.md) qua `hash = url_title_hash`

# Metrics

- [Dedup Rate](../metrics/dedup_rate.md)

[^dedup]: [DedupCache implementation](project/src/db/dedup.py)
[^db-store]: [ArticleStore schema DDL](project/src/db/store.py)
[^data-model]: [Data Model & DB Design](project/docs/dev/02-data-model-and-db.md)
