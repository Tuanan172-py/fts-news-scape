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
sources_last_checked: 2026-10-22
---

`project/config/settings.yaml` chứa cấu hình toàn cục, load bởi `src/core/config.py::load_settings()`
khi [Morninger](../pipelines/morninger.md) hoặc orchestrator khởi động.[^config-loader]

# Nội dung (rút gọn, bỏ chú thích)

```yaml
database:
  path: C:/data/news-scape/monocle.db   # MONOCLE_DB_PATH / MONOCLE_DATA_DIR ghi đè

logging:
  level: INFO               # thư mục log: <MONOCLE_DATA_DIR>/logs

scheduler:
  interval_minutes: 15      # orchestrator standalone

http:
  rate_limit: 3.0           # giây giữa 2 request cùng domain
  timeout: 30
  max_retries: 3

export:
  enabled: true             # <MONOCLE_DATA_DIR>/exports/articles-YYYY-MM-DD.csv, ghi đè mỗi cycle

morninger:
  capture_interval_minutes: 10
  rederive_interval_minutes: 30
  deferred_backfill_limit: 60
  deferred_budget_seconds: 90
  deferred_max_attempts: 5
  deferred_retry_window_hours: 24
  drift_hour: 6
  drift_minute: 0
  drift_limit: 100
```

Đường dẫn dữ liệu (log, export, notifications…) **không** khai trong file này: chúng do
`src/core/paths.py` suy từ `MONOCLE_DATA_DIR` (mặc định `C:\data\news-scape`). `database.path`
trong OneDrive hoặc trong kho mã bị `resolve_db_path` từ chối.

Các giá trị sau là **hằng số trong code**, không có khoá YAML:

| Hành vi | Nơi quy định |
|---|---|
| WAL, `busy_timeout=30000`, `synchronous=NORMAL` | `store._connect()` |
| Log rotation 50 MB, giữ 14 ngày | `src/core/logging.py` |
| `coalesce=True`, `max_instances=1`, misfire 300s | `morninger.build_scheduler()` / orchestrator |
| Xoay User-Agent, backoff | `src/crawler/http_client.py`, `src/crawler/backoff.py` |
| Stale lock scheduler 2400s, `capture.lock` | `src/core/proclock.py` |
| `reclaim_interval_minutes` (mặc định 30) | `morninger.build_scheduler()` |

# Các khối

| Khối | Ảnh hưởng tới |
|---|---|
| `database` | [Web Monocle DB](../datasets/web_monocle_db.md) |
| `logging` | Loguru sink `<DATA_ROOT>/logs/monocle.log` |
| `scheduler` | [Capture Orchestrator](../pipelines/ingestion_scheduler.md) chạy standalone |
| `http` | HTTPClient — rate limit / timeout / retry |
| `export` | CSV `articles-YYYY-MM-DD.csv` cuối mỗi cycle |
| `morninger` | job của [Morninger](../pipelines/morninger.md), gồm bù bài deferred sau capture |

Cấu hình tầng vận hành tự chủ nằm riêng ở `project/config/ops.yaml` (`src/core/ops_config.py`).

# Liên quan

- [secrets.yaml](secrets.md) · [watchlist.yaml](watchlist.md) · [notifications.yaml](notifications.md)
- [Domain configs](domain_sources.md) · [User subscriptions](user_subscriptions.md)

[^settings]: [settings.yaml](project/config/settings.yaml)
[^config-loader]: [config.py](project/src/core/config.py)
