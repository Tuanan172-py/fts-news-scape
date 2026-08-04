---
type: SQLite Table
title: seen_articles
description: Bảng kỹ thuật quản lý trạng thái xử lý và khử trùng lặp dữ liệu qua SHA-256 hash.
resource: project/data/monocle.db (table: seen_articles)
tags: [deduplication, sqlite, internal]
status: stable
generated:
  by: human:anpt
  at: 2026-08-03T10:00:00Z
sources:
  - id: data-model
    resource: project/docs/dev/02-data-model-and-db.md
    title: Data Model & DB Design
  - id: dedup
    resource: project/src/db/dedup.py
    title: 2-layer dedup implementation
sources_last_checked: 2026-08-03
---

Bảng `seen_articles` đóng vai trò là "Lớp 1" trong cơ chế Deduplication (khử trùng lặp) của hệ thống Web Monocle.[^dedup]

Mỗi khi một tin tức mới đi vào pipeline, một mã băm duy nhất bằng thuật toán SHA-256 sẽ được sinh ra từ việc ghép chuỗi `url` và `title`. Bảng này làm nhiệm vụ lưu trữ các mã băm đã từng đi qua hệ thống (exact match) giúp tiết kiệm tài nguyên lưu trữ và loại bỏ các thao tác API dư thừa đối với các nguồn tin cập nhật liên tục.[^dedup]

Cơ chế dedup có 2 lớp:
1. **Lớp 1 (DB)**: Kiểm tra `url_title_hash` trong `seen_articles` và `articles.url_title_hash` UNIQUE constraint
2. **Lớp 2 (Fuzzy)**: So sánh title bằng `rapidfuzz` nếu config `fuzzy_dedup: true` — phát hiện cùng bài nhưng URL khác nhau do tracking params[^dedup]

Cả 2 lớp đều hoạt động trong [DedupCache](../references/dedup_cache.md) được khởi tạo từ đầu chu kỳ, cache toàn bộ hash vào memory để tra cứu O(1).[^dedup]

# Schema

| Column | Type | Constraints | Description |
|---|---|---|---|
| `hash_id` | TEXT | PRIMARY KEY | SHA-256(`url` + `title`) |
| `title_norm` | TEXT | | Title đã normalize (lowercase, bỏ dấu) |
| `source_domain` | TEXT | | Tên miền nguồn |
| `seen_at` | TEXT | NOT NULL | Thời điểm đánh dấu đã xử lý |

# Joins

- JOIN với [articles](articles.md) qua `hash_id = url_title_hash` để trace bài báo đã xử lý

[^data-model]: [Data Model & DB Design](project/docs/dev/02-data-model-and-db.md)
[^dedup]: [Dedup implementation](project/src/db/dedup.py)
