---
type: SQLite Table
title: l1_tasks
description: Bảng legacy của hàng đợi Lớp 1 (đường L1/Gold đã khai tử); nay chỉ giữ tiêu đề đối chiếu cho cổng DoD nhận diện của Article Lane.
resource: "<DATA_ROOT>/monocle.db (table: l1_tasks)"
tags: [agent, l1, entity-recognition, legacy]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore schema DDL
  - id: l1-runner
    resource: project/src/agent/ingest/l1_runner.py
    title: L1Runner.ingest_output + _register_article_lane_task
  - id: l1-router
    resource: project/src/agent/contract/l1_router.py
    title: check_l1_dod
sources_last_checked: 2026-10-22
---

`l1_tasks` giữ **1 hàng / article** (`article_id` UNIQUE) cho bản ghi nhận diện thực thể.

> **Legacy.** Bảng sinh ra cho hàng đợi Lớp 1 của đường hai lớp L1/Gold (`l1_route.py`, đã xoá
> theo ADR-0010). Article Lane **không** dùng nó làm hàng đợi: Article Lane chọn bài từ
> `articles` + `work_items`. Bảng vẫn còn trong DDL vì cổng `L1Runner.ingest_output` cần một hàng
> để lấy tiêu đề đối chiếu: thiếu hàng thì `_register_article_lane_task` tự ghi một hàng
> `route = 'article_lane'`, tiêu đề lấy từ `articles`.[^l1-runner] Radar không đọc bảng này.

# Ý nghĩa cột hiện hành

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | |
| `article_id` | TEXT NOT NULL **UNIQUE** | = `articles.url_title_hash` |
| `domain` | TEXT | Tên miền nguồn |
| `title` | TEXT | Tiêu đề — văn bản để chấm grounding ở DoD nhận diện |
| `code_first_json` | TEXT | Kết quả code-first của đường cũ; `NULL` ở hàng Article Lane |
| `route` | TEXT | `article_lane` (hàng mới); `resolved` / `needs_agent` chỉ còn ở hàng lịch sử |
| `packet_path` | TEXT | Packet của đường cũ; `NULL` ở hàng Article Lane |
| `status` | TEXT NOT NULL DEFAULT pending | `pending` / `done` / `failed` — cập nhật sau DoD |
| `enqueued_at` | TEXT | Thời điểm ghi hàng |
| `done_at` | TEXT | Thời điểm ingest đạt DoD |
| `error` | TEXT | 3 lý do fail DoD đầu tiên (JSON) |

**Index:** `idx_l1_tasks_status` trên `(status, enqueued_at)`

# Common Query Patterns

### Phân bố theo route (phân biệt hàng lịch sử với hàng Article Lane)

```sql
SELECT route, status, COUNT(*) AS n
FROM l1_tasks
GROUP BY route, status ORDER BY n DESC;
```

Không dùng bảng này để đo tồn đọng: tồn đọng của Article Lane đọc bằng
`python scripts/pipeline_radar.py status` hoặc `python scripts/article_run.py --where`.

# Joins

- [articles](articles.md) qua `article_id = url_title_hash`
- [l1_outputs](l1_outputs.md) qua `article_id`

# Pipeline liên quan

- [Agent Ingest & cổng DoD](../pipelines/agent_handoff.md)

[^db-store]: [ArticleStore schema DDL](project/src/db/store.py)
[^l1-runner]: [L1Runner](project/src/agent/ingest/l1_runner.py)
[^l1-router]: [l1_router.py](project/src/agent/contract/l1_router.py)
