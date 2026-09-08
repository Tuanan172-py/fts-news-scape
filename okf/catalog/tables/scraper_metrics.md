---
type: SQLite Table
title: scraper_metrics
description: Log append-only mỗi chu kỳ thu thập — bài fetch được, bài mới, lỗi, thời lượng.
resource: "project/data/monocle.db (table: scraper_metrics)"
tags: [metrics, monitoring, scraper]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore schema DDL
  - id: heartbeat
    resource: project/src/monitor/heartbeat.py
    title: record_metrics()
  - id: orchestrator
    resource: project/src/orchestrator.py
    title: Orchestrator run_cycle
sources_last_checked: 2026-09-07
---

Bảng `scraper_metrics` ghi **1 hàng / (scraper × chu kỳ)** sau khi mỗi scraper kết thúc
`run()`.[^orchestrator] Append-only — dùng để dựng chuỗi thời gian hiệu suất, không upsert.

# Schema

| Column | Type | Constraints | Description |
|---|---|---|---|
| `ts` | TEXT | | Thời điểm chu kỳ (ISO 8601, giờ VN) |
| `scraper_name` | TEXT | | Tên config domain |
| `articles_fetched` | INTEGER | | Tổng bài lấy được từ list |
| `articles_new` | INTEGER | | Bài mới (qua được dedup) |
| `errors` | INTEGER | | Số lỗi trong chu kỳ |
| `duration_ms` | INTEGER | | Thời lượng chu kỳ (ms) |

**Index:** `idx_metrics_scraper` trên `(scraper_name, ts)`

⚠️ Bảng **không có** cột `id` và không có ràng buộc NOT NULL/DEFAULT — mọi cột đều nullable.

# Common Query Patterns

### Hiệu suất 24h

```sql
SELECT scraper_name,
       SUM(articles_fetched) AS fetched,
       SUM(articles_new)     AS new_,
       SUM(errors)           AS errs,
       ROUND(AVG(duration_ms)) AS avg_ms
FROM scraper_metrics
WHERE ts >= datetime('now', '-1 day', 'localtime')
GROUP BY scraper_name
ORDER BY new_ DESC;
```

### Tỷ lệ bài mới (nghịch đảo dedup rate)

```sql
SELECT scraper_name,
       ROUND(CAST(SUM(articles_new) AS REAL) / MAX(SUM(articles_fetched), 1) * 100, 1) AS new_pct
FROM scraper_metrics
WHERE ts >= datetime('now', '-7 days', 'localtime')
GROUP BY scraper_name;
```

# Metrics

- [Scraper Health](../metrics/scraper_health.md) · [Dedup Rate](../metrics/dedup_rate.md)

[^db-store]: [ArticleStore schema DDL](project/src/db/store.py)
[^heartbeat]: [Heartbeat + metrics](project/src/monitor/heartbeat.py)
[^orchestrator]: [Orchestrator](project/src/orchestrator.py)
