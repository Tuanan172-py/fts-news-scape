---
type: Metric
title: Scraper Health
description: Sức khỏe scraper — trạng thái hiện thời, error rate và latency theo chu kỳ.
tags: [metric, monitoring, scraper, health]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: heartbeat
    resource: project/src/monitor/heartbeat.py
    title: Heartbeat + record_metrics
  - id: health
    resource: project/src/monitor/health.py
    title: Health check CLI + ngưỡng
  - id: db-store
    resource: project/src/db/store.py
    title: DDL scraper_heartbeat / scraper_metrics
sources_last_checked: 2026-09-07
---

# Definition

Ba góc nhìn, **hai nguồn khác nhau**:

| Góc nhìn | Nguồn | Ghi chú |
|---|---|---|
| Trạng thái hiện thời | [scraper_heartbeat](../tables/scraper_heartbeat.md) | 1 hàng / scraper (upsert) ⇒ **không** tính uptime lịch sử từ bảng này |
| Error rate | [scraper_metrics](../tables/scraper_metrics.md) | append-only theo chu kỳ |
| Latency | [scraper_metrics](../tables/scraper_metrics.md) | `duration_ms` mỗi chu kỳ |

# Computation

### Trạng thái hiện thời

```sql
SELECT scraper_name, status, consecutive_failures, cycle_count, last_run_ts
FROM scraper_heartbeat
ORDER BY consecutive_failures DESC, last_run_ts;
```

### Tỷ lệ chu kỳ sạch (7 ngày) — proxy cho uptime

```sql
SELECT scraper_name,
       COUNT(*) AS cycles,
       SUM(CASE WHEN errors = 0 THEN 1 ELSE 0 END) AS clean_cycles,
       ROUND(SUM(CASE WHEN errors = 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS clean_pct
FROM scraper_metrics
WHERE ts >= datetime('now', '-7 days', 'localtime')
GROUP BY scraper_name
ORDER BY clean_pct;
```

### Error rate & latency (7 ngày)

```sql
SELECT scraper_name,
       SUM(errors) AS errs,
       SUM(articles_fetched) AS fetched,
       ROUND(CAST(SUM(errors) AS REAL) / MAX(SUM(articles_fetched), 1) * 100, 1) AS error_pct,
       ROUND(AVG(duration_ms)) AS avg_ms,
       MAX(duration_ms) AS max_ms
FROM scraper_metrics
WHERE ts >= datetime('now', '-7 days', 'localtime')
GROUP BY scraper_name
ORDER BY error_pct DESC;
```

CLI: `python -m src.monitor.health` (exit 0 = OK, 1 = có vấn đề).

# Target & Alert

Ngưỡng do `src/monitor/health.py` áp:

| Điều kiện | Mức |
|---|---|
| `consecutive_failures ≥ 3` | CRITICAL |
| `status = 'failed'` | FAILED |
| `last_run_ts` cũ hơn 30 phút | STALE |

Bổ sung khi xem báo cáo:

| Chỉ số | Target | Cảnh báo |
|---|---|---|
| `clean_pct` (7 ngày) | > 95% | < 90% |
| `error_pct` | < 5% | > 10% |
| `avg_ms` | < 30.000 ms/domain | > 60.000 ms (rate limit / timeout) |

⚠️ Giá trị `status` hợp lệ là `running` / `ok` / `failed` — **không** có `error`.

# Liên quan

- [scraper_heartbeat](../tables/scraper_heartbeat.md) · [scraper_metrics](../tables/scraper_metrics.md)
- [Runbook](../playbooks/runbook.md) · [Articles Per Day](articles_per_day.md)
