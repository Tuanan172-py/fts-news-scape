---
type: Metric
title: Articles Per Day
description: Số bài thu thập mỗi ngày theo nguồn — throughput của Vòng 1.
tags: [metric, ingestion, throughput]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: db-store
    resource: project/src/db/store.py
    title: DDL bảng articles
  - id: orchestrator
    resource: project/src/orchestrator.py
    title: Vòng ghi articles
  - id: daily-reporter
    resource: project/src/monitor/daily_reporter.py
    title: Analytics engine — báo cáo ngày
sources_last_checked: 2026-09-07
---

# Definition

Số bài **duy nhất** thu được mỗi ngày, group theo `source_domain`. Đo throughput của
[Capture Orchestrator](../pipelines/ingestion_scheduler.md).

Dùng `fetched_at` (thời điểm hệ thống lấy được) chứ không phải `published_at` — để đo *năng lực
thu thập*, không lẫn với độ trễ xuất bản của nguồn.

# Computation

```sql
SELECT date(fetched_at) AS day,
       source_domain,
       COUNT(*) AS article_count
FROM articles
WHERE fetched_at >= datetime('now', '-30 days', 'localtime')
GROUP BY day, source_domain
ORDER BY day DESC, article_count DESC;
```

Báo cáo dựng sẵn: `python scripts/monitor_daily.py --date today --save-md`.

# Target

- **7 domain đang bật:** vài trăm bài/ngày (mỗi feed ~30 item, nhiều feed/domain).
- Bất kỳ domain đang bật nào **= 0 bài trong 24h** ⇒ bất thường.

# Alert

- `article_count = 0` cho domain đang bật trong 24h ⇒ feed chết / selector hỏng / bị chặn.
  Đối chiếu [scraper_heartbeat](../tables/scraper_heartbeat.md) và trường `pitfalls` của YAML.
- Sụt >50% so với trung bình 7 ngày ⇒ kiểm tra nguồn đổi cấu trúc.

# Liên quan

- [articles](../tables/articles.md) · [Scraper Health](scraper_health.md) · [Dedup Rate](dedup_rate.md)
