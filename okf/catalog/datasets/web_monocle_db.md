---
type: SQLite Database
title: Web Monocle DB
description: SQLite duy nhất của hệ thống — 10 bảng phủ ingestion, change-detection, handoff agent và trạng thái điều phối.
resource: project/data/monocle.db
tags: [database, sqlite, news-scape, wal]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore — schema DDL + pragmas
  - id: writer
    resource: project/src/db/writer.py
    title: DBWriter single-writer
  - id: data-model
    resource: project/docs/dev/02-data-model-and-db.md
    title: Data Model & DB Design
  - id: db-handbook
    resource: project/docs/operations/monocle-db-handbook.md
    title: Monocle DB handbook
sources_last_checked: 2026-09-07
---

`data/monocle.db` là **cơ sở dữ liệu duy nhất** của hệ thống — standalone, không phụ thuộc dịch
vụ ngoài. Mọi connection đều bật `journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`
để đọc song song không bị chặn bởi ghi.[^db-store]

Ghi hàng loạt đi qua [DBWriter](../pipelines/db_writer.md) theo mẫu **single-writer** nhằm tránh
`SQLITE_BUSY`; các thao tác trạng thái (claim work_item, upsert lock) dùng `BEGIN IMMEDIATE`
riêng để giữ tính nguyên tử.[^writer]

Đây là *chỉ mục và trạng thái* của hệ, **không phải** nguồn provenance: bằng chứng bất biến nằm
ở [Bronze raw store](bronze_raw_html.md) trên đĩa.

# 10 bảng

| Tầng | Bảng | Mục đích |
|---|---|---|
| Bronze | [articles](../tables/articles.md) | bài đã capture + chuẩn hoá |
| Bronze | [seen_articles](../tables/seen_articles.md) | cache dedup SHA-256 |
| Bronze | [scraper_heartbeat](../tables/scraper_heartbeat.md) | trạng thái hiện thời từng scraper |
| Bronze | [scraper_metrics](../tables/scraper_metrics.md) | log hiệu suất mỗi chu kỳ |
| Silver | [article_versions](../tables/article_versions.md) | nhật ký capture + change-detection |
| Handoff | [work_items](../tables/work_items.md) | hàng đợi agent exactly-once |
| Gold L1 | [l1_tasks](../tables/l1_tasks.md) | hàng đợi nhận diện thực thể |
| Gold L1 | [l1_outputs](../tables/l1_outputs.md) | output L1 đã qua DoD |
| Gold L2 | [agent_outputs](../tables/agent_outputs.md) | output phân tích đã qua DoD |
| Điều phối | [pipeline_state](../tables/pipeline_state.md) | watermark, checkpoint, advisory lock |

⚠️ Bản mô tả cũ nhắc bảng `schema_version` — DDL hiện tại **không có** bảng này; phiên bản
schema (v2) là quy ước trong `store._SCHEMA`, không lưu trong DB.

# Cấu hình

| Thuộc tính | Giá trị | Nguồn |
|---|---|---|
| Đường dẫn | `data/monocle.db` | [settings.yaml](../configurations/settings.md) `database.path` |
| Journal mode | WAL | `store._connect()` |
| Busy timeout | 5000 ms | `store._connect()` |
| Synchronous | NORMAL | `store._connect()` |
| `check_same_thread` | False | APScheduler chạy job ở worker thread khác |

DB được `.gitignore`. Bản chụp point-in-time không chặn ghi: `scripts/db_snapshot.py`
(`src/db/snapshot.py`).

# Vận hành

```powershell
# tổng quan trạng thái mọi bảng + watermark
.venv\Scripts\python.exe scripts\db_status.py

# truy vấn nhanh
.venv\Scripts\python.exe scripts\dbq.py "SELECT COUNT(*) FROM articles"
```

Xem thêm: [Runbook](../playbooks/runbook.md), [Deployment](../playbooks/deployment.md).

[^db-store]: [ArticleStore](project/src/db/store.py)
[^writer]: [DBWriter](project/src/db/writer.py)
[^data-model]: [Data Model & DB Design](project/docs/dev/02-data-model-and-db.md)
[^db-handbook]: [Monocle DB handbook](project/docs/operations/monocle-db-handbook.md)
