---
type: Metric
title: Silver Backlog & Handoff Queue
description: Tồn đọng giữa các tầng — Bronze chưa re-derive, work_items pending/held/claimed treo.
tags: [metric, pipeline, backlog, handoff]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: derive
    resource: project/src/pipeline/derive.py
    title: Watermark + checkpoint
  - id: catalog
    resource: project/src/handoff/catalog.py
    title: Catalog.counts
  - id: daily-reporter
    resource: project/src/monitor/daily_reporter.py
    title: Đọc silver_watermark / silver_checkpoint
sources_last_checked: 2026-09-07
---

# Definition

Ba loại tồn đọng, mỗi loại chỉ ra một chỗ nghẽn khác nhau:

| Backlog | Nghĩa | Nghẽn ở |
|---|---|---|
| **Bronze chưa re-derive** | số `.meta.json` có `fetch_ts` > `silver_watermark` | Vòng 2 chạy chậm hơn Vòng 1 |
| **`work_items.pending`** | việc đã sẵn sàng, chưa agent nào nhận | Vòng 3 chưa chạy đủ nhịp |
| **`work_items.held`** | bài bị chặn bởi precondition | selector / template hỏng — cần người |

# Computation

### Hàng đợi handoff

```sql
SELECT status, COUNT(*) AS n FROM work_items GROUP BY status ORDER BY n DESC;
```

### Watermark & checkpoint Silver

```sql
SELECT key, value, updated_at FROM pipeline_state WHERE key LIKE 'silver_%';
```

`silver_checkpoint` được ghi khi backlog Bronze = 0. Checkpoint **cũ hơn nhiều giờ** trong khi
capture vẫn chạy ⇒ re-derive đang kẹt.

### Việc treo ở `claimed`

```sql
SELECT domain, COUNT(*) AS stuck
FROM work_items
WHERE status = 'claimed' AND claimed_at < datetime('now', '-6 hours', 'localtime')
GROUP BY domain ORDER BY stuck DESC;
```

### Held theo nguyên nhân

```sql
SELECT domain, change_state, COUNT(*) AS n
FROM work_items WHERE status = 'held'
GROUP BY domain, change_state ORDER BY n DESC;
```

Nhanh hơn: `python scripts/db_status.py`.

# Target & Alert

| Chỉ số | Target | Cảnh báo |
|---|---|---|
| Backlog Bronze | ≈ 0 sau mỗi nhịp re-derive 30′ | tăng liên tục qua 3 nhịp |
| `pending` | giảm về ~0 sau mỗi lô agent | tích luỹ nhiều ngày |
| `claimed` quá 6 giờ | 0 | > 0 ⇒ agent chết giữa chừng |
| `held` | ổn định, không tăng | tăng đột biến ở 1 domain ⇒ trang đổi giao diện |

`held` tăng vọt là tín hiệu **hành động**: sửa `detail.content_selector` trong
[domain config](../configurations/domain_sources.md), rồi chạy
`scripts/rederive_from_bronze.py <domain>`.

# Liên quan

- [work_items](../tables/work_items.md) · [pipeline_state](../tables/pipeline_state.md)
- [Silver Derive](../pipelines/silver_derive.md) · [Runbook](../playbooks/runbook.md)
