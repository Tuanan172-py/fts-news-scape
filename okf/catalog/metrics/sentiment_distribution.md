---
type: Metric
title: Sentiment Distribution
description: Phân phối cảm xúc của tin theo nguồn — nay tính từ agent_outputs (Gold), không còn từ cột articles.sentiment.
tags: [metric, sentiment, agent, gold]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: db-store
    resource: project/src/db/store.py
    title: DDL agent_outputs / articles
  - id: user-output
    resource: project/src/export/user_output.py
    title: Flatten sentiment.polarity
  - id: agent-io
    resource: project/docs/design/09-agent-io-contract.md
    title: Agent I/O contract — trường sentiment
sources_last_checked: 2026-09-07
---

# Definition

Tỷ trọng `positive` / `negative` / `neutral` của tin theo nguồn.

> ⚠️ **Nguồn tính đã đổi (2026-09).** Engine rule-based đã gỡ khỏi workflow nên
> `articles.sentiment` chỉ còn giá trị lịch sử. Sentiment hiện hành nằm trong
> [agent_outputs](../tables/agent_outputs.md) `output_json.sentiment.polarity`, chỉ có ở bài đã
> qua DoD.

# Computation

### Nguồn hiện hành (Gold, đã qua DoD)

```sql
SELECT a.source_domain,
       json_extract(ag.output_json, '$.sentiment.polarity') AS polarity,
       COUNT(*) AS n
FROM agent_outputs ag
JOIN articles a ON a.url_title_hash = ag.article_id
WHERE ag.dod_pass = 1
  AND ag.created_at >= datetime('now', '-7 days', 'localtime')
GROUP BY a.source_domain, polarity
ORDER BY a.source_domain, n DESC;
```

### Nguồn lịch sử (legacy rule-based)

```sql
SELECT source_domain, sentiment, COUNT(*) AS n
FROM articles
WHERE sentiment IS NOT NULL
GROUP BY source_domain, sentiment;
```

Chỉ dùng để so sánh dữ liệu cũ — cột này không còn được ghi mới.

# Diễn giải

- Mẫu **thiên lệch có chủ đích**: chỉ bài được giao agent mới có sentiment, mà việc giao agent
  ưu tiên bài chạm subscription người dùng.
- Chỉ tính hàng `dod_pass = 1`; hàng fail DoD có thể chứa sentiment bịa, không đưa vào thống kê.
- Nhiều `polarity` rỗng ⇒ agent bỏ trống trường tuỳ chọn này, không phải lỗi pipeline.

# Alert

- Một nguồn có >90% cùng một `polarity` trong 7 ngày ⇒ nghi prompt lệch hoặc payload bị cắt.
- Tỷ lệ `polarity` rỗng tăng đột biến ⇒ kiểm tra prompt/schema của agent Gold.

# Liên quan

- [agent_outputs](../tables/agent_outputs.md) · [DoD Pass Rate](dod_pass_rate.md)
- [Sentiment Pipeline (legacy)](../pipelines/sentiment_pipeline.md)
