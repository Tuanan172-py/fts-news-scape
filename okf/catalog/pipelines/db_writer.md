---
type: Python Pipeline
title: DBWriter — Single-Writer Thread
description: Daemon thread duy nhất ghi bảng articles, gom batch ≤50 hoặc mỗi 2s vào 1 transaction.
resource: project/src/db/writer.py
tags: [pipeline, sqlite, writer, concurrency]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: writer
    resource: project/src/db/writer.py
    title: DBWriter implementation
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore.insert_batch
  - id: orchestrator
    resource: project/src/orchestrator.py
    title: Orchestrator — enqueue/flush/stop
sources_last_checked: 2026-09-07
---

`DBWriter` là **daemon thread duy nhất** ghi bảng [articles](../tables/articles.md). Scraper
không bao giờ ghi DB trực tiếp — chỉ trả `ScrapeResult`, orchestrator `enqueue()`. Mục đích:
tránh `SQLITE_BUSY` khi nhiều scraper chạy nối tiếp trong cùng tiến trình.[^writer]

# Luồng

```
Orchestrator                         db-writer thread
    │                                     │  (connection RIÊNG của thread)
    ├─ enqueue(article) ─► queue.Queue ──►│ _drain_batch():
    │   (_pending += 1)                   │   chờ item đầu ≤ 2s, gom tối đa 50
    │                                     │ store.insert_batch(batch, conn)
    │                                     │   (_pending -= len(batch); notify)
    ├─ flush(timeout=10s) ───────────────►│ chặn tới khi _pending == 0
    ├─ _export_csv() / _wal_checkpoint()  │
    └─ stop(timeout=30s) ────────────────►│ set stop → xả hết queue → join
```

`flush()` dùng `threading.Condition` đếm `_pending`, **không** phải sleep — bảo đảm mọi bài của
cycle đã commit trước khi export CSV và WAL checkpoint.[^writer]

# Tham số

| Thuộc tính | Giá trị | Ghi chú |
|---|---|---|
| Thread | `daemon=True`, tên `db-writer` | tự kết thúc khi main thoát |
| `batch_size` | 50 | gom tối đa mỗi transaction |
| `flush_interval` | 2.0 s | thời gian chờ item đầu tiên |
| `flush()` timeout | 10 s | trả False nếu quá hạn |
| `stop()` timeout | 30 s | quá hạn ⇒ log WARNING kèm số item còn lại |
| Insert | `INSERT OR IGNORE` | trùng `url`/`url_title_hash` ⇒ bỏ qua |

Connection của thread writer là **riêng biệt** (`store._connect()`), mở suốt đời thread.

# Tương tác

- **Orchestrator** — `enqueue()` mỗi bài mới; `flush()` trước export; `stop()` khi shutdown.
- **Scrapers** — không chạm DB.
- **ArticleStore** — `insert_batch()` chỉ có consumer duy nhất là DBWriter.

⚠️ Chỉ bảng `articles` đi qua DBWriter. Các bảng trạng thái (heartbeat, metrics, work_items,
l1/agent outputs, pipeline_state) được ghi trực tiếp bằng connection ngắn hạn + `BEGIN IMMEDIATE`
khi cần nguyên tử.

# Quan hệ

- Ghi vào [Web Monocle DB](../datasets/web_monocle_db.md) / [articles](../tables/articles.md)
- Được điều phối bởi [Capture Orchestrator](ingestion_scheduler.md)

[^writer]: [DBWriter](project/src/db/writer.py)
[^db-store]: [ArticleStore](project/src/db/store.py)
[^orchestrator]: [Orchestrator](project/src/orchestrator.py)
