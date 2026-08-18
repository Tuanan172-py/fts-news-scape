---
type: Metric
title: Scraper Health
description: Trạng thái sức khỏe của các scraper — uptime, error rate, latency.
tags: [metric, monitoring, scraper, health]
status: stable
generated:
  by: human:anpt
  at: 2026-08-04T00:00:00Z
sources:
  - id: scraper-heartbeat
    resource: ../tables/scraper_heartbeat.md
    title: Scraper heartbeat table
  - id: scraper-metrics
    resource: ../tables/scraper_metrics.md
    title: Scraper metrics table
sources_last_checked: 2026-08-04
---

# Definition

Tổng hợp sức khỏe của tất cả scraper đang active, bao gồm:

1. **Uptime**: % chu kỳ thành công trong 24h qua
2. **Error rate**: Tỷ lệ lỗi / tổng bài fetch
3. **Latency**: Thời gian chạy trung bình mỗi chu kỳ

# Computation

### Uptime (24h)

```sql
SELECT
  scraper_name,
  COUNT(*) AS total_cycles,
  SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) AS ok_cycles,
  ROUND(SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS uptime_pct
FROM scraper_heartbeat
WHERE last_run_ts >= datetime('now', '-1 day', 'localtime')
GROUP BY scraper_name;
```

### Error Rate (7 ngày)

```sql
SELECT
  scraper_name,
  SUM(errors) AS total_errors,
  SUM(articles_fetched) AS total_fetched,
  ROUND(CAST(SUM(errors) AS REAL) / MAX(SUM(articles_fetched), 1) * 100, 1) AS error_rate_pct
FROM scraper_metrics
WHERE ts >= datetime('now', '-7 days', 'localtime')
GROUP BY scraper_name;
```

### Latency Trung bình (7 ngày)

```sql
SELECT
  scraper_name,
  ROUND(AVG(duration_ms), 0) AS avg_duration_ms,
  MAX(duration_ms) AS max_duration_ms
FROM scraper_metrics
WHERE ts >= datetime('now', '-7 days', 'localtime')
GROUP BY scraper_name
ORDER BY avg_duration_ms DESC;
```

# Target

| Chỉ số | Target | Alert |
|---|---|---|
| Uptime | > 95% | < 90% trong 24h |
| Error rate | < 5% | > 10% trong 24h |
| Latency | < 30s/domain | > 60s (có thể bị rate limit hoặc timeout) |
| Consecutive failures | 0 | >= 3 → scraper cần investigation |

# Alert

- **Critical**: Bất kỳ domain active nào có `consecutive_failures >= 5`
- **Warning**: `uptime_pct < 90%` hoặc `error_rate > 10%`
