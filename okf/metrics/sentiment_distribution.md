---
type: Metric
title: Sentiment Distribution
description: Phân phối cảm xúc (positive/negative/neutral) của bài báo theo nguồn trong 7 ngày qua.
tags: [metric, sentiment, nlp]
status: stable
generated:
  by: human:anpt
  at: 2026-08-04T00:00:00Z
sources:
  - id: articles-table
    resource: ../tables/articles.md
    title: Articles table
  - id: sentiment-pipeline
    resource: ../pipelines/sentiment_pipeline.md
    title: Sentiment pipeline
sources_last_checked: 2026-08-04
---

# Definition

Phân phối phần trăm của 3 nhãn cảm xúc (positive, negative, neutral) theo từng source_domain. Đo lường "tone" của tin tức từ mỗi nguồn.

# Computation

```sql
SELECT
  source_domain,
  sentiment,
  COUNT(*) AS count,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY source_domain), 1) AS pct
FROM articles
WHERE published_at >= datetime('now', '-7 days', 'localtime')
  AND sentiment IS NOT NULL
GROUP BY source_domain, sentiment
ORDER BY source_domain, count DESC;
```

# Interpretation

| Pattern | Interpretation |
|---|---|
| Positive > 60% | Nguồn có xu hướng lạc quan |
| Negative > 40% | Nguồn có xu hướng bi quan / cảnh báo |
| Neutral > 70% | Nguồn thiên về đưa tin khách quan |
| Phân bố đều (~33% mỗi loại) | Nguồn cân bằng |

# Alert

Theo dõi sentiment shift đột ngột — nếu positive giảm >20pp trong 1 tuần, có thể có sự kiện thị trường bất lợi.
