---
type: Metric
title: Articles Per Day
description: Số lượng bài báo được thu thập mỗi ngày, phân theo source_domain.
tags: [metric, ingestion, throughput]
status: stable
generated:
  by: human:anpt
  at: 2026-08-04T00:00:00Z
sources:
  - id: articles-table
    resource: ../tables/articles.md
    title: Articles table
sources_last_checked: 2026-08-04
---

# Definition

Số lượng bài báo duy nhất được thu thập mỗi ngày, group by `source_domain`. Đo lường throughput của pipeline ingestion.

# Computation

```sql
SELECT
  date(fetched_at) AS day,
  source_domain,
  COUNT(*) AS article_count
FROM articles
WHERE day >= date('now', '-30 days', 'localtime')
GROUP BY day, source_domain
ORDER BY day DESC, article_count DESC;
```

# Target

- **Hiện tại (2 domain active):** >50 articles/day
- **Phase 2 (20 domain active):** >500 articles/day

# Alert

Cảnh báo nếu `article_count = 0` cho bất kỳ domain active nào trong 24h qua → scraper có thể bị lỗi hoặc bị chặn.
