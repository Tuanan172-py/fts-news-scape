---
type: SQLite Table
title: articles
description: Bảng trung tâm lưu trữ thông tin bài viết và tin tức thị trường chứng khoán từ 23 nguồn.
resource: project/data/monocle.db (table: articles)
tags: [news, stock-market, raw-data, enriched]
status: stable
generated:
  by: human:anpt
  at: 2026-08-03T10:00:00Z
sources:
  - id: data-model
    resource: project/docs/dev/02-data-model-and-db.md
    title: Data Model & DB Design
    author: human:anpt
  - id: system-overview
    resource: project/docs/design/01-system-overview.md
    title: System Overview
    author: human:anpt
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore schema DDL
sources_last_checked: 2026-08-03
---

Bảng `articles` lưu trữ thông tin chi tiết về các bài viết chứng khoán được thu thập từ 23 nguồn dữ liệu khác nhau bao gồm RSS, REST API, và HTML scraping.[^system-overview] Hạt độ (grain) của bảng là mỗi bản ghi tương ứng với một bài viết duy nhất được xác định bởi `url`.

Dữ liệu trong bảng tuân theo nguyên lý "Không vứt dữ liệu" (Graceful degradation). Cụ thể, bảng bao gồm cả HTML thô nguyên bản (`content_html`) và văn bản đã được làm sạch (`content_text`) thông qua thư viện Trafilatura. Việc populate dữ liệu được thực hiện hoàn toàn tự động thông qua tiến trình [DBWriter](../pipelines/db_writer.md) chạy đơn luồng.[^db-store]

Bảng thuộc schema v2 của [Web Monocle DB](../datasets/web_monocle_db.md). Mỗi article sau khi được scraper thu thập sẽ trải qua pipeline: fetch → parse → dedup → [classify](../pipelines/sentiment_pipeline.md) → [sentiment](../pipelines/sentiment_pipeline.md) → DBWriter.[^system-overview]

# Schema

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | ID tự tăng |
| `url` | TEXT | UNIQUE NOT NULL | URL gốc của bài viết |
| `title` | TEXT | NOT NULL | Tiêu đề bài viết |
| `source_domain` | TEXT | NOT NULL | Tên miền nguồn (VD: cafef.vn) |
| `summary` | TEXT | | Tóm tắt (fallback khi enrich lỗi) |
| `content_html` | TEXT | | Nội dung HTML gốc (luôn giữ lại) |
| `content_text` | TEXT | | Nội dung văn bản sạch (Trafilatura) |
| `published_at` | TEXT | | Thời gian xuất bản (ISO 8601, giờ VN) |
| `author` | TEXT | | Tác giả bài viết |
| `symbols` | TEXT | | Mã CK liên quan (phân tách dấu phẩy) |
| `categories` | TEXT | | Nhãn phân loại (phân tách dấu phẩy) |
| `sentiment` | TEXT | | Phân loại cảm xúc: positive/negative/neutral |
| `sentiment_score` | REAL | | Điểm số cảm xúc (-1.0 đến 1.0) |
| `fetched_at` | TEXT | NOT NULL | Thời gian hoàn tất fetch (ISO 8601, giờ VN) |
| `processed_at` | TEXT | | Thời gian xử lý & làm giàu thành công |
| `metadata` | TEXT | | JSON dump chứa metadata bổ sung |
| `url_title_hash` | TEXT | UNIQUE | SHA-256(url + title) — dùng cho dedup |

**Indexes:**
- `idx_articles_url` trên `url`
- `idx_articles_source_domain` trên `source_domain`
- `idx_articles_published_at` trên `published_at`

# Common Query Patterns

### Bài báo mới nhất có sentiment tích cực

```sql
SELECT title, url, source_domain, published_at, sentiment_score
FROM articles
WHERE sentiment = 'positive' AND symbols IS NOT NULL
ORDER BY published_at DESC
LIMIT 10;
```

### Thống kê bài báo theo sentiment trong 7 ngày qua

```sql
SELECT
  sentiment,
  source_domain,
  COUNT(*) AS article_count
FROM articles
WHERE published_at >= date('now', '-7 days')
GROUP BY sentiment, source_domain
ORDER BY article_count DESC;
```

### Bài báo trùng lặp (cùng URL được scrape nhiều lần)

```sql
SELECT url, COUNT(*) AS occurrences
FROM articles
GROUP BY url
HAVING COUNT(*) > 1;
```

# Joins

- JOIN với [seen_articles](seen_articles.md) qua `url_title_hash = hash_id` để kiểm tra trạng thái dedup
- JOIN với [scraper_metrics](scraper_metrics.md) qua `source_domain` để theo dõi hiệu suất thu thập

# Metrics

Các metrics được tính từ bảng này:
- [Articles Per Day](../metrics/articles_per_day.md) — số lượng bài báo thu thập mỗi ngày
- [Sentiment Distribution](../metrics/sentiment_distribution.md) — phân phối cảm xúc theo nguồn

[^data-model]: [Data Model & DB Design](project/docs/dev/02-data-model-and-db.md)
[^system-overview]: [System Overview](project/docs/design/01-system-overview.md)
[^db-store]: [ArticleStore implementation](project/src/db/store.py)
