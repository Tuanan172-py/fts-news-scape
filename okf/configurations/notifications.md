---
type: Configuration
title: Notifications
description: Cấu hình thông báo 4-tier — watchlist → symbol → finance-source → market-keyword.
resource: project/config/notifications.yaml
tags: [config, yaml, notifications, alerting]
status: stable
generated:
  by: human:anpt
  at: 2026-08-04T00:00:00Z
sources:
  - id: notifications-config
    resource: project/config/notifications.yaml
    title: Notifications config
  - id: notifier
    resource: project/src/notifier/file_notify.py
    title: FileNotifier implementation
  - id: notification-design
    resource: project/docs/design/05-notification-coverage.md
    title: Notification Coverage Design
sources_last_checked: 2026-08-04
---

Hệ thống thông báo 4-tier giúp lọc và ưu tiên tin tức dựa trên mức độ liên quan đến danh mục đầu tư.[^notification-design]

# 4 Tiers

| Tier | Trigger | Mức độ | Hành động |
|---|---|---|---|
| **Tier 1 — Watchlist** | Bài báo đề cập trực tiếp mã trong [watchlist](watchlist.md) | 🔴 Cao nhất | Ghi file `.txt` ngay lập tức |
| **Tier 2 — Symbol** | Bài báo đề cập bất kỳ mã chứng khoán nào | 🟠 Cao | Ghi file `.txt` |
| **Tier 3 — Finance Source** | Bài báo từ nguồn tài chính được phân loại `finance` | 🟡 Trung bình | Ghi file `.txt` |
| **Tier 4 — Market Keyword** | Bài báo chứa từ khóa thị trường | 🟢 Thấp | Chỉ log, không notify |

# Cấu trúc

```yaml
notifications:
  enabled: true
  output_dir: "data/notifications/"
  tiers:
    watchlist:
      enabled: true
      prefix: "WATCHLIST"
    symbol:
      enabled: true
      prefix: "SYMBOL"
    finance_source:
      enabled: true
      prefix: "FINANCE"
    market_keyword:
      enabled: false
      prefix: "MARKET"
  keywords:
    - "VN-Index"
    - "HOSE"
    - "HNX"
    - "lãi suất"
    - "tỷ giá"
```

# Output

File notification được ghi vào `data/notifications/` với format:
```
WATCHLIST_20260804_143000.txt
SYMBOL_20260804_143000.txt
FINANCE_20260804_143000.txt
```

Mỗi file chứa danh sách bài báo khớp trong chu kỳ đó.

# Implementation

[FileNotifier](../references/codebase.md) (`src/notifier/file_notify.py`) được gọi bởi [Orchestrator](../pipelines/ingestion_scheduler.md) sau khi tất cả scraper hoàn thành 1 chu kỳ.

[^notifications-config]: [Notifications config](project/config/notifications.yaml)
[^notifier]: [FileNotifier implementation](project/src/notifier/file_notify.py)
[^notification-design]: [Notification Coverage Design](project/docs/design/05-notification-coverage.md)
