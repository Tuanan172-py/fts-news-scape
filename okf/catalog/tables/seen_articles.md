---
type: SQLite Table
title: seen_articles
description: Cache khử trùng lặp lớp 1 — hash SHA-256(url+title) đã đi qua pipeline.
resource: "project/data/monocle.db (table: seen_articles)"
tags: [deduplication, sqlite, internal]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: dedup
    resource: project/src/db/dedup.py
    title: DedupCache — 2-layer dedup
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore schema DDL
  - id: data-model
    resource: project/docs/dev/02-data-model-and-db.md
    title: Data Model & DB Design
sources_last_checked: 2026-09-07
---

Bảng `seen_articles` là **lớp 1** của cơ chế dedup. Mỗi bài đi qua pipeline sinh 1 hash
SHA-256(`url` + `title`); hash đã có ⇒ bỏ qua, không fetch trang chi tiết, không ghi
[articles](articles.md).[^dedup]

Dedup 2 lớp:[^dedup]
1. **Lớp 1 (exact)** — `seen_articles.hash` + UNIQUE `articles.url_title_hash`.
2. **Lớp 2 (fuzzy)** — so tiêu đề đã normalize (`title_norm`) bằng `rapidfuzz`, bật qua
   config domain `fuzzy_dedup: true`; bắt trường hợp cùng bài nhưng URL khác (tracking params).

`DedupCache` nạp toàn bộ hash vào memory đầu chu kỳ để tra cứu O(1), ghi ngược lại DB trong
cùng SQLite (WAL-safe) — không còn file JSON như bản cũ.[^dedup]

# Schema

| Column | Type | Constraints | Description |
|---|---|---|---|
| `hash` | TEXT | PRIMARY KEY | SHA-256(`url` + `title`) |
| `title_norm` | TEXT | | Tiêu đề đã normalize (lowercase, bỏ dấu) — đầu vào fuzzy |
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
