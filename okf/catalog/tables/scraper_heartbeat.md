---
type: SQLite Table
title: scraper_heartbeat
description: Bảng theo dõi trạng thái chạy của từng scraper — last run, status, số lần fail liên tiếp.
resource: "project/data/monocle.db (table: scraper_heartbeat)"
tags: [monitoring, heartbeat, scraper]
status: stable
generated:
  by: human:anpt
  at: 2026-08-04T00:00:00Z
sources:
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore schema DDL
  - id: heartbeat
    resource: project/src/monitor/heartbeat.py
    title: Heartbeat monitoring module
sources_last_checked: 2026-08-04
---

Bảng `scraper_heartbeat` ghi lại trạng thái của mỗi scraper sau mỗi chu kỳ. Được cập nhật bởi module [Heartbeat](../references/monitoring.md) trong mỗi lần orchestrator chạy.[^heartbeat]

Dùng để:
- Phát hiện scraper bị lỗi liên tục (`consecutive_failures >= 3`)
- Theo dõi thời gian chạy cuối cùng của từng domain
- Tính uptime và reliability

# Schema

| Column | Type | Constraints | Description |
|---|---|---|---|
| `scraper_name` | TEXT | PRIMARY KEY | Tên domain (VD: cafef, vietstock) |
| `last_run_ts` | TEXT | NOT NULL | Thời gian chạy cuối cùng (ISO 8601) |
| `status` | TEXT | NOT NULL | Trạng thái: ok / error |
| `error_msg` | TEXT | | Thông báo lỗi (nếu có) |
| `consecutive_failures` | INTEGER | DEFAULT 0 | Số lần fail liên tiếp |
| `cycle_count` | INTEGER | DEFAULT 0 | Tổng số chu kỳ đã chạy |

# Common Query Patterns

### Kiểm tra scraper đang fail

```sql
SELECT scraper_name, status, error_msg, consecutive_failures
FROM scraper_heartbeat
WHERE status = 'error'
ORDER BY consecutive_failures DESC;
```

### Scraper lâu không chạy (> 1 giờ)

```sql
SELECT scraper_name, last_run_ts
FROM scraper_heartbeat
WHERE last_run_ts < datetime('now', '-1 hour', 'localtime');
```

[^db-store]: [ArticleStore schema DDL](project/src/db/store.py)
[^heartbeat]: [Heartbeat monitoring](project/src/monitor/heartbeat.py)
