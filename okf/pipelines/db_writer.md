---
type: Python Pipeline
title: DBWriter — Single-Writer Thread
description: Background thread duy nhất ghi dữ liệu vào SQLite, nhận articles qua queue.Queue từ orchestrator.
resource: project/src/db/writer.py
tags: [pipeline, sqlite, writer, concurrency]
status: stable
generated:
  by: human:anpt
  at: 2026-08-04T00:00:00Z
sources:
  - id: writer
    resource: project/src/db/writer.py
    title: DBWriter implementation
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore
sources_last_checked: 2026-08-04
---

`DBWriter` là một daemon thread chạy nền, đảm nhận toàn bộ việc ghi dữ liệu vào [SQLite](../datasets/web_monocle_db.md). Đây là giải pháp "Single-writer" để tránh lỗi `SQLITE_BUSY` khi nhiều scraper cùng ghi đồng thời.[^writer]

# Luồng hoạt động

```
Orchestrator                          DBWriter Thread
    │                                      │
    ├── scraper.run() → articles           │
    ├── writer.enqueue(article) ──────────►│ queue.Queue
    ├── writer.enqueue(article) ──────────►│
    │    ...                               │
    │                                      ├── _run() loop:
    │                                      │   while not stopped:
    │                                      │     batch = drain(queue, max=50)
    │                                      │     if batch:
    │                                      │       store.insert_batch(batch)
    │                                      │       COMMIT
    │                                      │     else:
    │                                      │       sleep(2s)
    │                                      │
    ├── writer.flush() ───────────────────►│ drain ALL + commit
    │                                      │
    ├── writer.stop() ────────────────────►│ set stop flag + join thread
```

# Đặc điểm kỹ thuật

| Thuộc tính | Giá trị | Mô tả |
|---|---|---|
| Thread type | `daemon=True` | Tự động kết thúc khi main thread exit |
| Batch size | 50 articles | Ghi batch để tối ưu transaction |
| Drain interval | 2 giây | Nếu queue rỗng, nghỉ 2s trước khi kiểm tra lại |
| Transaction mode | `BEGIN IMMEDIATE` | Tránh deadlock với reader khác |
| Flush timeout | 10 giây | Thời gian chờ tối đa khi flush |
| Stop timeout | 30 giây | Thời gian chờ thread join khi shutdown |

# Tương tác với hệ thống

- **Orchestrator**: Gọi `enqueue()` cho mỗi article mới, `flush()` trước CSV export, `stop()` khi shutdown
- **Scrapers**: KHÔNG ghi trực tiếp vào DB — chỉ trả về `ScrapeResult` cho orchestrator
- **ArticleStore**: `DBWriter` là consumer duy nhất của `insert_batch()`

# Quan hệ

- Đọc/ghi vào [Web Monocle DB](../datasets/web_monocle_db.md)
- Được điều phối bởi [Orchestrator](ingestion_scheduler.md)
- Ghi vào bảng [articles](../tables/articles.md), [scraper_heartbeat](../tables/scraper_heartbeat.md), [scraper_metrics](../tables/scraper_metrics.md)

[^writer]: [DBWriter implementation](project/src/db/writer.py)
[^db-store]: [ArticleStore](project/src/db/store.py)
