---
type: Metric
title: Dedup Rate
description: Tỷ lệ khử trùng lặp — phần trăm bài báo bị loại bỏ do đã tồn tại trong hệ thống.
tags: [metric, dedup, efficiency]
status: stable
generated:
  by: human:anpt
  at: 2026-08-04T00:00:00Z
sources:
  - id: scraper-metrics
    resource: ../tables/scraper_metrics.md
    title: Scraper metrics table
  - id: dedup
    resource: project/src/db/dedup.py
    title: Dedup implementation
sources_last_checked: 2026-08-04
---

# Definition

Tỷ lệ bài báo bị dedup loại bỏ so với tổng số bài fetch được trong 7 ngày qua. `Dedup Rate = 1 - (articles_new / articles_fetched)`.

Dedup rate cao (>80%) là bình thường với nguồn RSS cập nhật thường xuyên. Dedup rate thấp bất thường (<20%) có thể báo hiệu dedup cache bị lỗi.

# Computation

```sql
SELECT
  scraper_name,
  SUM(articles_fetched) AS total_fetched,
  SUM(articles_new) AS total_new,
  ROUND((1.0 - CAST(SUM(articles_new) AS REAL) / MAX(SUM(articles_fetched), 1)) * 100, 1) AS dedup_pct
FROM scraper_metrics
WHERE ts >= datetime('now', '-7 days', 'localtime')
GROUP BY scraper_name
ORDER BY dedup_pct DESC;
```

# Target

- **RSS sources:** 50-90% dedup rate (bình thường)
- **API sources:** 30-70% dedup rate

# Alert

Cảnh báo nếu dedup rate < 10% trong 24h → dedup cache có thể chưa được load đúng cách.
