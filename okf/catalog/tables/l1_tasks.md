---
type: SQLite Table
title: l1_tasks
description: Hàng đợi Lớp 1 (nhận diện thực thể theo tiêu đề) — kết quả code-first + trạng thái tra soát của agent.
resource: "project/data/monocle.db (table: l1_tasks)"
tags: [agent, l1, entity-recognition, queue]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore schema DDL
  - id: l1-runner
    resource: project/src/agent/l1_runner.py
    title: L1Runner — route_and_export / ingest_output
  - id: l1-router
    resource: project/src/agent/l1_router.py
    title: Quy trình 2 tầng code-first → handoff
  - id: l1-classifier
    resource: project/src/agent/l1_classifier.py
    title: Bước code-first deterministic
sources_last_checked: 2026-09-07
---

`l1_tasks` giữ **1 hàng / article** cho Lớp 1 — nhận diện thực thể tài chính trong **tiêu đề**.
Khác [work_items](work_items.md) (khoá kép article+raw), ở đây `article_id` là UNIQUE: L1 chỉ
quan tâm tiêu đề nên không phụ thuộc bản raw.[^l1-runner]

# Quy trình 2 tầng

| Tầng | Thực hiện | Kết quả |
|---|---|---|
| **1 — code-first** | `l1_classifier` khớp mã + alias trong tiêu đề, hoàn toàn deterministic, không LLM | `route = resolved` nếu khớp ≥1 entity |
| **2 — handoff** | Tiêu đề code không khớp ⇒ phát task-packet `data/agent_tasks/l1/<id>.task.json` cho agent tra soát | `route = needs_agent` |

Chế độ phát packet (`scripts/l1_route.py --review`):[^l1-runner]
- `all` — phát cho **mọi** tin, agent được quyền tra soát cả tin đã `resolved`.
- `missed` — chỉ phát cho tin code-first không khớp.

`status` là trạng thái *tra soát của agent*: `pending` → `done` / `failed`. Một bài có
`route=resolved` vẫn ở `pending` cho tới khi agent nộp output và qua DoD.

# Schema

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | |
| `article_id` | TEXT NOT NULL **UNIQUE** | = `articles.url_title_hash` |
| `domain` | TEXT | Tên miền nguồn |
| `title` | TEXT | Tiêu đề — cũng là văn bản để chấm grounding ở DoD |
| `code_first_json` | TEXT | Kết quả code-first (entities / industries / relevance) |
| `route` | TEXT | `resolved` / `needs_agent` |
| `packet_path` | TEXT | Đường dẫn packet đã phát (NULL nếu không phát) |
| `status` | TEXT NOT NULL DEFAULT pending | `pending` / `done` / `failed` |
| `enqueued_at` | TEXT | Thời điểm route |
| `done_at` | TEXT | Thời điểm ingest thành công |
| `error` | TEXT | 3 lý do fail DoD đầu tiên (JSON) |

**Index:** `idx_l1_tasks_status` trên `(status, enqueued_at)`

# Common Query Patterns

### Tồn đọng L1 theo route

```sql
SELECT route, status, COUNT(*) AS n
FROM l1_tasks
GROUP BY route, status ORDER BY n DESC;
```

### Tin code-first không nhận ra entity (cần agent)

```sql
SELECT article_id, domain, title
FROM l1_tasks
WHERE route = 'needs_agent' AND status = 'pending'
ORDER BY enqueued_at DESC LIMIT 50;
```

# Joins

- [articles](articles.md) qua `article_id = url_title_hash`
- [l1_outputs](l1_outputs.md) qua `article_id`

# Pipeline liên quan

- [Agent Handoff](../pipelines/agent_handoff.md)

[^db-store]: [ArticleStore schema DDL](project/src/db/store.py)
[^l1-runner]: [L1Runner](project/src/agent/l1_runner.py)
[^l1-router]: [l1_router.py](project/src/agent/l1_router.py)
[^l1-classifier]: [l1_classifier.py](project/src/agent/l1_classifier.py)
