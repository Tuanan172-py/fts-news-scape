---
type: Configuration
title: Global Settings
description: Cấu hình toàn cục hệ thống Web Monocle — DB path, logging, scheduler, HTTP, export.
resource: project/config/settings.yaml
tags: [config, yaml, global]
status: stable
generated:
  by: human:anpt
  at: 2026-08-04T00:00:00Z
sources:
  - id: settings
    resource: project/config/settings.yaml
    title: Global settings file
sources_last_checked: 2026-08-04
---

File `config/settings.yaml` chứa toàn bộ cấu hình toàn cục của hệ thống. Được load bởi `src/core/config.py` khi orchestrator khởi động.[^settings]

# Cấu trúc

```yaml
database:
  path: "data/monocle.db"
  wal: true
  busy_timeout: 5000

logging:
  level: "INFO"
  rotation: "50 MB"
  retention: "14 days"
  path: "logs/orchestrator.log"

scheduler:
  interval_minutes: 15
  coalesce: true
  max_instances: 1

http:
  default_rate_limit: 3.0    # giây
  default_timeout: 30        # giây
  max_retries: 3
  backoff_factor: 1.5
  user_agent_rotation: true

export:
  csv_enabled: true
  csv_path: "data/exports/"
```

# Các section chính

| Section | Mô tả |
|---|---|
| `database` | [SQLite DB](../datasets/web_monocle_db.md) path, WAL mode, busy timeout |
| `logging` | [Loguru](../references/monitoring.md) config — level, rotation, retention |
| `scheduler` | [APScheduler](../pipelines/ingestion_scheduler.md) — interval, coalesce |
| `http` | [HTTPClient](../references/codebase.md) — rate limit, timeout, retry |
| `export` | [CSV Export](../references/codebase.md) config |

# Liên quan

- [secrets.yaml](secrets.md) — API tokens
- [watchlist.yaml](watchlist.md) — Danh sách mã theo dõi
- [notifications.yaml](notifications.md) — Cấu hình thông báo
- [Domain configs](domain_sources.md) — 23 domain YAML files

[^settings]: [Global settings](project/config/settings.yaml)
