---
type: Metric
title: Sentiment Distribution
description: Phân phối cảm xúc của tin theo nguồn — tính từ agent_outputs (bản nội dung đã qua DoD), không từ cột articles.sentiment.
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
    title: Đọc sentiment dạng chuỗi (v2-lean) hoặc sentiment.polarity (v1)
sources_last_checked: 2026-10-22
---

# Definition

Tỷ trọng `positive` / `negative` / `neutral` của tin theo nguồn.

Sentiment do mô hình sinh trong [Article Lane](../pipelines/article_lane.md) và nằm trong
[agent_outputs](../tables/agent_outputs.md): `output_json.sentiment` là chuỗi ở
`agent-output-v2-lean`, `output_json.sentiment.polarity` ở v1. Engine rule-based đã xoá;
`articles.sentiment` chỉ còn giá trị lịch sử.

# Computation

### Nguồn hiện hành (Gold, đã qua DoD)

```sql
SELECT a.source_domain,
       CASE json_type(ag.output_json, '$.sentiment')
            WHEN 'text' THEN json_extract(ag.output_json, '$.sentiment')
            ELSE json_extract(ag.output_json, '$.sentiment.polarity') END AS polarity,
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

- Mẫu **thiên lệch có chủ đích**: chỉ bài đã qua Article Lane mới có sentiment, và Article Lane
  xếp tầng ưu tiên theo danh mục người dùng.
- Chỉ tính hàng `dod_pass = 1`; hàng fail DoD có thể chứa sentiment bịa, không đưa vào thống kê.
- Nhiều `polarity` rỗng ở hàng v1 ⇒ trường tuỳ chọn bị bỏ trống; ở v2-lean `sentiment` là bắt buộc.

# Alert

- Một nguồn có >90% cùng một `polarity` trong 7 ngày ⇒ nghi prompt lệch hoặc payload bị cắt.
- Tỷ lệ `polarity` rỗng tăng đột biến ⇒ kiểm tra persona/prefix và bước expand.

# Liên quan

- [agent_outputs](../tables/agent_outputs.md) · [DoD Pass Rate](dod_pass_rate.md)
- Engine rule-based cũ: đã lưu trữ ở `okf/archive/catalog/pipelines/sentiment_pipeline.md`
