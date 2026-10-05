---
type: SQLite Table
title: articles
description: Bảng trung tâm lưu bài viết đã capture + chuẩn hoá; hạt độ = 1 bài / url.
resource: "project/data/monocle.db (table: articles)"
tags: [news, stock-market, bronze, articles]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore schema DDL (_SCHEMA)
  - id: models
    resource: project/src/core/models.py
    title: Article dataclass + url_title_hash
  - id: data-model
    resource: project/docs/dev/02-data-model-and-db.md
    title: Data Model & DB Design
sources_last_checked: 2026-09-07
---

Bảng `articles` lưu mỗi bài viết thu được ở **Vòng 1 — Capture**. Hạt độ: 1 hàng = 1 bài,
định danh nghiệp vụ là `url_title_hash` = SHA-256(`url` + `title`) — khoá này xuyên suốt mọi
tầng (Bronze → Silver → work_items → l1_outputs/agent_outputs → CSV người dùng).[^db-store]

Ghi vào bảng **chỉ** qua [DBWriter](../pipelines/db_writer.md) (single-writer thread) bằng
`INSERT OR IGNORE` trên tập 16 cột nghiệp vụ (`id` tự sinh).[^db-store] Scraper không bao giờ
ghi DB trực tiếp.

Nguyên tắc "không vứt dữ liệu": `content_html` giữ bản HTML đã bóc, `content_text` là bản sạch
(Trafilatura). Bản raw **byte-exact** không nằm ở đây mà ở tầng
[Bronze raw store](../datasets/bronze_raw_html.md) — `articles` là chỉ mục tra cứu, không phải
nguồn provenance.

> Từ 2026-09: `sentiment` / `sentiment_score` do engine rule-based sinh **đã gỡ khỏi workflow**
> (xem [Sentiment Pipeline](../pipelines/sentiment_pipeline.md) — trạng thái legacy). Sentiment
> "thật" dùng cho deliverable nằm ở [agent_outputs](agent_outputs.md), không ở cột này.

# Schema

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | ID tự tăng |
| `url` | TEXT | NOT NULL UNIQUE | URL gốc bài viết |
| `url_title_hash` | TEXT | NOT NULL UNIQUE | SHA-256(url + title) — `article_id` toàn hệ |
| `title` | TEXT | NOT NULL | Tiêu đề |
| `summary` | TEXT | | Tóm tắt từ feed (fallback khi enrich lỗi) |
| `content_html` | TEXT | | HTML nội dung bài |
| `content_text` | TEXT | | Văn bản sạch (Trafilatura) |
| `published_at` | TEXT | | Thời gian xuất bản (ISO 8601, giờ VN) |
| `author` | TEXT | | Tác giả |
| `source_domain` | TEXT | NOT NULL | Tên miền nguồn (vd `cafef.vn`) |
| `symbols` | TEXT | | Mã CK gắn được (phân tách dấu phẩy) |
| `categories` | TEXT | | Nhãn phân loại (phân tách dấu phẩy) |
| `sentiment` | TEXT | | *legacy* — positive/negative/neutral |
| `sentiment_score` | REAL | | *legacy* — điểm −1.0…1.0 |
| `fetched_at` | TEXT | NOT NULL | Thời điểm fetch xong (ISO 8601, giờ VN) |
| `processed_at` | TEXT | | Thời điểm enrich/xử lý xong |
| `metadata_json` | TEXT | | JSON metadata bổ sung |

**Indexes:**
- `idx_articles_published` trên `published_at`
- `idx_articles_source` trên `(source_domain, fetched_at)`
- UNIQUE ngầm trên `url` và `url_title_hash`

⚠️ Cột tên là `metadata_json` (không phải `metadata`); index KHÔNG có `idx_articles_url` riêng —
UNIQUE constraint đã tạo index ngầm.

# Common Query Patterns

### Sản lượng theo nguồn trong ngày

```sql
SELECT source_domain, COUNT(*) AS n
FROM articles
WHERE date(fetched_at) = date('now', 'localtime')
GROUP BY source_domain
ORDER BY n DESC;
```

### Bài đã qua đủ 2 lớp agent (điều kiện vào deliverable)

```sql
SELECT a.url_title_hash, a.title, a.source_domain
FROM articles a
JOIN l1_outputs    l1 ON l1.article_id = a.url_title_hash AND l1.dod_pass = 1
JOIN agent_outputs ag ON ag.article_id = a.url_title_hash AND ag.dod_pass = 1
WHERE date(COALESCE(a.published_at, a.fetched_at)) = date('now', 'localtime');
```

### Bài chưa có bản Silver/work_item (rò rỉ pipeline)

```sql
SELECT a.url_title_hash, a.source_domain, a.fetched_at
FROM articles a
LEFT JOIN work_items w ON w.article_id = a.url_title_hash
WHERE w.id IS NULL AND a.fetched_at >= datetime('now', '-1 day', 'localtime');
```

# Joins

- [seen_articles](seen_articles.md) qua `url_title_hash = hash` — trạng thái dedup
- [article_versions](article_versions.md) qua `url_title_hash` — lịch sử capture / change-detect
- [work_items](work_items.md), [l1_tasks](l1_tasks.md), [l1_outputs](l1_outputs.md),
  [agent_outputs](agent_outputs.md) qua `article_id = url_title_hash`
- [scraper_metrics](scraper_metrics.md) qua `source_domain ↔ scraper_name` (**không** luôn bằng
  nhau: `scraper_name` là tên config, vd `tnck` ↔ `source_domain` `tinnhanhchungkhoan.vn`)

# Metrics

- [Articles Per Day](../metrics/articles_per_day.md)
- [Sentiment Distribution](../metrics/sentiment_distribution.md)

[^db-store]: [ArticleStore schema DDL](project/src/db/store.py)
[^models]: [Article model](project/src/core/models.py)
[^data-model]: [Data Model & DB Design](project/docs/dev/02-data-model-and-db.md)
