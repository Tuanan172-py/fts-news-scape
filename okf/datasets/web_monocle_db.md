---
type: SQLite Database
title: Web Monocle DB
description: Cơ sở dữ liệu SQLite chính lưu trữ tin tức và quản lý trạng thái của hệ thống Web Monocle.
resource: data/monocle.db
tags: [database, sqlite, news-scape, wal]
status: stable
generated:
  by: human:anpt
  at: 2026-08-03T10:00:00Z
sources:
  - id: data-model
    resource: project/docs/dev/02-data-model-and-db.md
    title: Data Model & DB Design
    author: human:anpt
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore SQLite schema implementation
sources_last_checked: 2026-08-03
---

Web Monocle DB là cơ sở dữ liệu SQLite duy nhất được hệ thống Web Monocle sử dụng. Cơ sở dữ liệu này hoạt động ở chế độ Write-Ahead Logging (WAL) để cho phép đọc song song trong khi đang xử lý ghi, giúp hạn chế vấn đề locking của SQLite.[^data-model]

Database này được thiết kế theo nguyên tắc "Single-writer" thông qua thread [DBWriter](../pipelines/db_writer.md) nhằm tối ưu hóa multi-writer coordination và tránh lỗi `SQLITE_BUSY`.[^data-model]

# Schema

Database bao gồm 5 bảng chính:

| Bảng | Mục đích |
|---|---|
| [articles](../tables/articles.md) | Tin tức đã thu thập và làm giàu |
| [seen_articles](../tables/seen_articles.md) | Cache khử trùng lặp SHA-256 |
| [scraper_heartbeat](../tables/scraper_heartbeat.md) | Trạng thái chạy của từng scraper |
| [scraper_metrics](../tables/scraper_metrics.md) | Metrics mỗi chu kỳ thu thập |
| schema_version | Phiên bản schema (v2) |

# Configuration

Được cấu hình qua [settings.yaml](../configurations/settings.md):

- **Journal Mode**: WAL
- **Busy Timeout**: 5000ms
- **Synchronous**: NORMAL
- **DB Path**: `data/monocle.db`
- **WAL Checkpoint**: Tự động sau mỗi chu kỳ hoặc khi DB đạt 100MB

[^data-model]: [Data Model & DB Design](project/docs/dev/02-data-model-and-db.md)
[^db-store]: [ArticleStore implementation](project/src/db/store.py)
