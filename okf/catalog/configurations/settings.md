---
type: Configuration
title: Global Settings
description: Cấu hình toàn cục — DB path, logging, scheduler, HTTP, export CSV, nhịp Morninger.
resource: project/config/settings.yaml
tags: [config, yaml, global]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: settings
    resource: project/config/settings.yaml
    title: Global settings file
  - id: config-loader
    resource: project/src/core/config.py
    title: Config loaders
sources_last_checked: 2026-09-07
---

`config/settings.yaml` chứa cấu hình toàn cục, load bởi `src/core/config.py::load_settings()`
khi [Morninger](../pipelines/morninger.md) hoặc orchestrator khởi động.[^config-loader]

# Nội dung thực tế

```yaml
database:
  path: data/monocle.db

logging:
  level: INFO
  dir: logs

scheduler:
  interval_minutes: 15     # chu kỳ capture

http:
  rate_limit: 3.0          # giây giữa 2 request cùng domain
  timeout: 30
  max_retries: 3

export:
  enabled: true            # tự xuất CSV 'hôm nay' cuối mỗi cycle
  dir: data/exports        # data/exports/articles-YYYY-MM-DD.csv (ghi đè mỗi cycle)

morninger:
  capture_interval_minutes: 15   # nhịp capture Bronze (job 1)
  rederive_interval_minutes: 30  # nhịp re-derive Silver tăng dần (job 2)
  drift_hour: 6                  # giờ chạy drift report mỗi sáng (job 3)
  drift_minute: 0
  drift_limit: 100
```

⚠️ File **không** khai báo `database.wal` / `busy_timeout`, cũng không có `logging.rotation`,
`scheduler.coalesce`, `http.backoff_factor`, `user_agent_rotation`, `export.csv_path`. Các giá
trị đó là **hằng số trong code**:

| Hành vi | Nơi quy định |
|---|---|
| WAL, `busy_timeout=5000`, `synchronous=NORMAL` | `store._connect()` |
| Log rotation 50 MB, giữ 14 ngày | `src/core/logging.py` |
| `coalesce=True`, `max_instances=1`, misfire 300s | `orchestrator.start_scheduler()` |
| Xoay User-Agent, backoff | `src/crawler/http_client.py` |
| Stale lock scheduler 2400s | `src/core/proclock.py` |

# Các khối

| Khối | Ảnh hưởng tới |
|---|---|
| `database` | [Web Monocle DB](../datasets/web_monocle_db.md) |
| `logging` | Loguru sink (`logs/`) |
| `scheduler` | [Capture Orchestrator](../pipelines/ingestion_scheduler.md) |
| `http` | HTTPClient — rate limit / timeout / retry |
| `export` | CSV `articles-YYYY-MM-DD.csv` cuối mỗi cycle |
| `morninger` | 3 job của [Morninger](../pipelines/morninger.md) |

# Liên quan

- [secrets.yaml](secrets.md) · [watchlist.yaml](watchlist.md) · [notifications.yaml](notifications.md)
- [Domain configs](domain_sources.md) · [User subscriptions](user_subscriptions.md)

[^settings]: [settings.yaml](project/config/settings.yaml)
[^config-loader]: [config.py](project/src/core/config.py)
