---
type: SQLite Table
title: scraper_metrics
description: Bảng ghi metrics mỗi chu kỳ thu thập của từng scraper — số bài fetched, new, errors, duration.
resource: "project/data/monocle.db (table: scraper_metrics)"
tags: [metrics, monitoring, scraper]
status: stable
generated:
  by: human:anpt
  at: 2026-08-04T00:00:00Z
sources:
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore schema DDL
  - id: orchestrator
    resource: project/src/orchestrator.py
    title: Orchestrator metrics collection
sources_last_checked: 2026-08-04
---

Bảng `scraper_metrics` ghi lại số liệu chi tiết của mỗi chu kỳ thu thập, được insert sau khi mỗi scraper hoàn thành `run()`.[^orchestrator]

Dùng để:
- Theo dõi hiệu suất thu thập theo thời gian (trend)
- Phát hiện domain có tỷ lệ bài mới thấp bất thường
- Đo latency và error rate

# Schema

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| `ts` | TEXT | NOT NULL | Timestamp chu kỳ (ISO 8601) |
| `scraper_name` | TEXT | NOT NULL | Tên domain |
| `articles_fetched` | INTEGER | DEFAULT 0 | Tổng số bài đã fetch |
| `articles_new` | INTEGER | DEFAULT 0 | Số bài mới (chưa có trong dedup) |
| `errors` | INTEGER | DEFAULT 0 | Số lỗi trong chu kỳ |
| `duration_ms` | INTEGER | | Thời gian chạy (milliseconds) |

# Common Query Patterns

### Hiệu suất 24h qua

```sql
SELECT scraper_name,
  SUM(articles_fetched) AS total_fetched,
  SUM(articles_new) AS total_new,
  AVG(duration_ms) AS avg_duration_ms
FROM scraper_metrics
WHERE ts >= datetime('now', '-1 day', 'localtime')
GROUP BY scraper_name
ORDER BY total_new DESC;
```

### Tỷ lệ bài mới / tổng bài fetch (dedup efficiency)

```sql
SELECT scraper_name,
  ROUND(CAST(SUM(articles_new) AS REAL) / MAX(SUM(articles_fetched), 1) * 100, 1) AS new_pct
FROM scraper_metrics
WHERE ts >= datetime('now', '-7 days', 'localtime')
GROUP BY scraper_name;
```

[^db-store]: [ArticleStore schema DDL](project/src/db/store.py)
[^orchestrator]: [Orchestrator](project/src/orchestrator.py)
