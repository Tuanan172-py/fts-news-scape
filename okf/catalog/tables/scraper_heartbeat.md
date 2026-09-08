---
type: SQLite Table
title: scraper_heartbeat
description: Trạng thái chạy hiện tại của từng scraper — last run, status, số lần fail liên tiếp.
resource: "project/data/monocle.db (table: scraper_heartbeat)"
tags: [monitoring, heartbeat, scraper]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore schema DDL
  - id: heartbeat
    resource: project/src/monitor/heartbeat.py
    title: Heartbeat + metrics module
  - id: health
    resource: project/src/monitor/health.py
    title: Health check CLI
sources_last_checked: 2026-09-07
---

Bảng `scraper_heartbeat` giữ **1 hàng / scraper** (upsert theo `scraper_name`), cập nhật mỗi
lần orchestrator chạy xong 1 domain.[^heartbeat] Đây là bảng trạng thái *hiện thời* — muốn xem
lịch sử theo chu kỳ dùng [scraper_metrics](scraper_metrics.md).

Dùng để: phát hiện scraper fail liên tiếp (`consecutive_failures >= 3`), biết domain nào lâu
không chạy, và cấp dữ liệu cho `python -m src.monitor.health`.[^health]

# Schema

| Column | Type | Constraints | Description |
|---|---|---|---|
| `scraper_name` | TEXT | PRIMARY KEY | Tên **config** domain (vd `cafef`, `tnck`) |
| `last_run_ts` | TEXT | | Thời điểm chạy gần nhất (ISO 8601, giờ VN) |
| `status` | TEXT | | `running` \| `ok` \| `failed` |
| `error_msg` | TEXT | | Thông báo lỗi gần nhất |
| `consecutive_failures` | INTEGER | DEFAULT 0 | Số chu kỳ fail liên tiếp |
| `cycle_count` | INTEGER | DEFAULT 0 | Tổng số chu kỳ đã chạy |

⚠️ Giá trị `status` là `running` / `ok` / `failed` (không phải `error`) — truy vấn cũ lọc
`status='error'` sẽ luôn rỗng.

# Common Query Patterns

### Scraper đang hỏng

```sql
SELECT scraper_name, status, consecutive_failures, error_msg
FROM scraper_heartbeat
WHERE status = 'failed' OR consecutive_failures >= 3
ORDER BY consecutive_failures DESC;
```

### Scraper kẹt / lâu không chạy (>1 giờ)

```sql
SELECT scraper_name, status, last_run_ts
FROM scraper_heartbeat
WHERE last_run_ts < datetime('now', '-1 hour', 'localtime')
ORDER BY last_run_ts;
```

# Metrics

- [Scraper Health](../metrics/scraper_health.md)

[^db-store]: [ArticleStore schema DDL](project/src/db/store.py)
[^heartbeat]: [Heartbeat monitoring](project/src/monitor/heartbeat.py)
[^health]: [Health check CLI](project/src/monitor/health.py)
